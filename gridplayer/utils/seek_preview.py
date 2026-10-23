"""Pictures of a video at a time, for the seek bar's hover label.

A frame is read by VLC in a process of its own, as FileLengths reads how long
files are: a file VLC chokes on takes that down rather than the player, and
the file is not asked about again. The process opens the file at each time
asked and takes the first frame drawn; asked faster than it reads, it reads
the last time asked and lets the ones before it go.

Files on disk only: a stream would be fetched a second time to be seen.
"""

import contextlib
import ctypes
import logging
import threading
from collections import OrderedDict
from multiprocessing import get_context
from pathlib import Path

from PyQt5.QtCore import QObject, pyqtSignal
from PyQt5.QtGui import QImage

_log = logging.getLogger(__name__)

# How big the frames are read, at most: drawn at half that in the label, which
# keeps them sharp on a screen of twice the pixels
PREVIEW_READ_PX = 320

# How long a frame is waited for, the file opened and decoded up to the time
FRAME_TIMEOUT_S = 3.0

# Nothing asked for this long, the file is let go of; the process stays
IDLE_RELEASE_S = 20.0

# How many frames are kept, for the mouse going back over where it has been
FRAMES_KEPT = 64


class SeekPreviewer(QObject):
    """Frames of files at times, read in a process of its own.

    Asked with request(), the frame comes to the callback given, on the GUI
    thread; only the last one to ask is answered, the mouse being over one
    seek bar at a time. A frame that cannot be read does not come at all.
    """

    # (path, time_ms, picture), from the thread reading the answers
    _frame_read = pyqtSignal(object, int, QImage)

    def __init__(self, parent=None):
        super().__init__(parent)

        self._lock = threading.Lock()

        self._process = None
        self._conn = None

        self._frames: OrderedDict[tuple[Path, int], QImage] = OrderedDict()

        # files the process could not open, or went down on
        self._unreadable: set[Path] = set()

        # the file the process was last sent, which it went down on, if it did
        self._sent_path: Path | None = None

        self._receiver = None

        self._frame_read.connect(self._on_frame_read)

    def is_readable(self, path: Path) -> bool:
        return path not in self._unreadable

    def request(self, path: Path, time_ms: int, receiver):
        """The frame of a file at a time, to receiver(path, time_ms, image)."""

        self._receiver = receiver

        frame = self._frames.get((path, time_ms))
        if frame is not None:
            self._frames.move_to_end((path, time_ms))
            receiver(path, time_ms, frame)
            return

        if path in self._unreadable:
            return

        conn = self._connection()
        if conn is None:
            return

        try:
            conn.send((str(path), time_ms))
        except (OSError, ValueError) as e:
            _log.warning(f"Seek preview not asked: {e}")
            return

        with self._lock:
            self._sent_path = path

    def close(self):
        self._receiver = None

        with self._lock:
            process, conn = self._process, self._conn
            self._process = self._conn = None

        if conn is not None:
            with contextlib.suppress(OSError, ValueError):
                conn.send(None)
            conn.close()

        if process is not None:
            process.join(1)
            if process.is_alive():
                process.terminate()

    def _connection(self):
        with self._lock:
            if self._conn is not None:
                return self._conn

            context = get_context("spawn")
            conn, child_conn = context.Pipe()

            process = context.Process(
                target=serve, args=(child_conn,), name="SeekPreview", daemon=True
            )

            try:
                process.start()
            except OSError as e:
                _log.warning(f"Seek preview process not started: {e}")
                return None
            finally:
                child_conn.close()

            self._process, self._conn = process, conn

        threading.Thread(
            target=self._read_answers, args=(conn,), name="SeekPreview", daemon=True
        ).start()

        return conn

    def _read_answers(self, conn):
        while True:
            try:
                answer = conn.recv()
            except (EOFError, OSError):
                break

            path, time_ms, width, height, data = answer
            path = Path(path)

            if data is None:
                # one whose first frame could not be read, not asked again
                if width == -1:
                    with self._lock:
                        self._unreadable.add(path)
                continue

            image = QImage(data, width, height, width * 4, QImage.Format_RGB32)

            self._frame_read.emit(path, time_ms, image.copy())

        self._process_gone(conn)

    def _process_gone(self, conn):
        with self._lock:
            if self._conn is not conn:
                # closed on purpose
                return

            _log.warning(f"Seek preview process went down on {self._sent_path}")

            if self._sent_path is not None:
                self._unreadable.add(self._sent_path)

            self._process = self._conn = None

    def _on_frame_read(self, path, time_ms, image):
        self._frames[(path, time_ms)] = image
        while len(self._frames) > FRAMES_KEPT:
            self._frames.popitem(last=False)

        if self._receiver is not None:
            self._receiver(path, time_ms, image)


def serve(conn):
    """Run in the process SeekPreviewer keeps: answers each (path, time_ms)
    with (path, time_ms, width, height, frame bytes), the frame None where it
    could not be read, and width -1 where the file could not be opened."""

    from gridplayer.vlc_player.libvlc import vlc

    instance = vlc.Instance(
        [
            "--intf=dummy",
            "--quiet",
            "--no-audio",
            "--no-spu",
            "--no-osd",
            "--no-lua",
            "--no-interact",
            "--no-sub-autodetect-file",
            "--no-video-title-show",
            # a picture or two now and then, the GPU is for the videos
            "--avcodec-hw=none",
        ]
    )

    grabber = _FrameGrabber(vlc, instance)

    try:
        while True:
            if not conn.poll(IDLE_RELEASE_S):
                grabber.let_go()
                conn.poll(None)

            asked = conn.recv()

            # only the last one asked by now is read
            while asked is not None and conn.poll():
                asked = conn.recv()

            if asked is None:
                break

            path, time_ms = asked

            conn.send((path, time_ms, *grabber.frame(path, time_ms)))
    except (EOFError, OSError):
        pass
    finally:
        grabber.let_go()


# vendored VideoFormatCb uses c_char_p for chroma, which ctypes converts to
# bytes so writes never reach VLC: a raw pointer instead, as ImageDecoder
_VideoFormatCb = ctypes.CFUNCTYPE(
    ctypes.c_uint,
    ctypes.POINTER(ctypes.c_void_p),
    ctypes.c_void_p,
    ctypes.POINTER(ctypes.c_uint),
    ctypes.POINTER(ctypes.c_uint),
    ctypes.POINTER(ctypes.c_uint),
    ctypes.POINTER(ctypes.c_uint),
)


def preview_size(width: int, height: int, most: int = PREVIEW_READ_PX):
    """A frame's size scaled down to fit in most by most, as it is shaped;
    never up."""

    if width <= 0 or height <= 0:
        return 0, 0

    scale = min(1.0, most / max(width, height))

    return max(2, round(width * scale)), max(2, round(height * scale))


class _FrameGrabber:
    """The first frame VLC draws of a file opened at a time.

    Opened there rather than sought to: a player sought while paused can
    still draw a frame of where it was first, where one opened at a time
    starts decoding there. A file on disk opens in a tenth of a second or so.
    VLC draws into a buffer of ours, scaled down to a preview's size.
    """

    def __init__(self, vlc, instance):
        self._vlc = vlc
        self._instance = instance

        self._player = instance.media_player_new()

        self._is_playing = False

        self._buffer = None
        self._size = (0, 0)

        self._is_wanted = False
        self._got = threading.Event()
        self._frame = None

        self._format_cb = self._make_format_cb()
        self._cleanup_cb = vlc.CallbackDecorators.VideoCleanupCb(lambda opaque: None)
        self._lock_cb = vlc.CallbackDecorators.VideoLockCb(self._on_lock)
        self._unlock_cb = vlc.CallbackDecorators.VideoUnlockCb(self._on_unlock)

        self._player.video_set_callbacks(self._lock_cb, self._unlock_cb, None, None)
        self._player.video_set_format_callbacks(self._format_cb, self._cleanup_cb)

    def frame(self, path: str, time_ms: int):
        """(width, height, frame bytes) of the file at the time; (0, 0,
        None) where none came in time, (-1, -1, None) where VLC got nowhere
        near a picture: a file it cannot open, or one with no video."""

        self.let_go()

        media = self._instance.media_new_path(path)
        media.add_option(":no-audio")
        media.add_option(f":start-time={time_ms / 1000:.3f}")
        self._player.set_media(media)
        media.release()

        self._frame = None
        self._size = (0, 0)
        self._got.clear()
        self._is_wanted = True

        self._player.play()
        self._is_playing = True

        is_got = self._got.wait(FRAME_TIMEOUT_S)

        self._is_wanted = False

        if is_got:
            return self._frame

        if self._size == (0, 0):
            return -1, -1, None

        return 0, 0, None

    def let_go(self):
        if not self._is_playing:
            return

        self._player.stop()
        self._is_playing = False

    def _make_format_cb(self):
        @_VideoFormatCb
        def _cb(opaque, chroma, width, height, pitches, lines):
            ctypes.memmove(chroma, b"RV32", 4)

            frame_width, frame_height = preview_size(width[0], height[0])
            if not frame_width:
                return 0

            # VLC scales to the size given back
            width[0] = frame_width
            height[0] = frame_height
            pitches[0] = frame_width * 4
            lines[0] = frame_height

            self._buffer = ctypes.create_string_buffer(frame_width * frame_height * 4)
            self._size = (frame_width, frame_height)

            return 1

        return _cb

    def _on_lock(self, opaque, planes):
        planes[0] = ctypes.addressof(self._buffer)
        return None

    def _on_unlock(self, opaque, picture, planes):
        if not self._is_wanted:
            return

        self._is_wanted = False
        width, height = self._size
        self._frame = (width, height, self._buffer.raw)
        self._got.set()
