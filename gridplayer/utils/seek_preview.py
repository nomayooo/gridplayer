"""Pictures of a video at a time, for the seek bar's hover label.

A frame is read by VLC in a process of its own, as FileLengths reads how long
files are: a file VLC chokes on takes that down rather than the player, and
the file is not asked about again. The process opens the file at each time
asked and takes the first frame drawn; asked faster than it reads, it reads
the last time asked and lets the ones before it go.

Files on disk only: a stream would be fetched a second time to be seen.
"""

import contextlib
import logging
import threading
from collections import OrderedDict
from multiprocessing import get_context
from pathlib import Path

from PyQt5.QtCore import QObject, pyqtSignal
from PyQt5.QtGui import QImage

from gridplayer.utils.seek_preview_reader import serve

_log = logging.getLogger(__name__)

# How many frames are kept, for the mouse going back over where it has been:
# a megabyte or so each
FRAMES_KEPT = 32


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

    def warm_up(self):
        """Start the process ahead of the first frame asked of it, which
        would otherwise wait for it to start: a second or more on Windows."""

        self._connection()

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
