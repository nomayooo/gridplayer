"""The frames of SeekPreviewer (see seek_preview), read by VLC in the process
it keeps: no Qt in here, for the process to start as quickly as it can.
"""

import ctypes
import threading
from pathlib import Path

# How big the frames are read, at most: drawn at half that in the label, which
# keeps them sharp on a screen of twice the pixels
PREVIEW_READ_PX = 640

# How long a frame is waited for, the file opened and decoded up to the time
FRAME_TIMEOUT_S = 3.0

# Nothing asked for this long, the file is let go of; the process stays
IDLE_RELEASE_S = 20.0


def serve(conn):
    """Run in the process SeekPreviewer keeps: answers each (path, time_ms)
    with (path, time_ms, width, height, frame bytes), the frame None where it
    could not be read, and width -1 where the file could not be opened."""

    from gridplayer.vlc_player.libvlc import vlc

    options = [
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

    # as the players: the plugins VLC found before, not looked for again
    if (
        vlc.plugin_path is not None
        and (Path(vlc.plugin_path) / "plugins.dat").is_file()
    ):
        options.append("--no-plugins-scan")

    instance = vlc.Instance(options)

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
