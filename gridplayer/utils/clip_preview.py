"""A video shown moving, a few seconds at each of a few places in it, for
Manage Favourites to show the one under the mouse.

Played by VLC in a process of its own (see clip_preview_reader), as the seek
bar's frames are read: a file VLC chokes on takes that down rather than the
player, and is not shown again. One file is shown at a time; asked for
another, the one before stops.
"""

import contextlib
import itertools
import logging
import random
import threading
from multiprocessing import get_context
from pathlib import Path

from PyQt5.QtCore import QObject, pyqtSignal
from PyQt5.QtGui import QImage

from gridplayer.utils.clip_preview_reader import serve

_log = logging.getLogger(__name__)

# how many places are shown, and how long each
PLACES = 4
SECONDS_EACH = 2.5

# kept clear of its very start and end, often black or titles
MARGIN = 0.05


def random_places(count: int = PLACES, rng=random) -> list[float]:
    """Places to show, as fractions of a video's length: one somewhere in
    each of `count` stretches of it, first to last, so that all of it is
    seen."""

    span = (1 - 2 * MARGIN) / count

    return [MARGIN + span * (i + rng.random()) for i in range(count)]


class ClipPreviewer(QObject):
    # a frame of the file being shown, on the GUI thread
    frame = pyqtSignal(QImage)

    # the file being shown cannot be: no picture came of it
    failed = pyqtSignal()

    _answer = pyqtSignal(object)

    def __init__(self, parent=None):
        super().__init__(parent)

        self._lock = threading.Lock()
        self._process = None
        self._conn = None

        self._tokens = itertools.count(1)
        self._token = None
        self._path: Path | None = None

        # files the process could not show, or went down on
        self._unreadable: set[Path] = set()

        self._answer.connect(self._on_answer)

    @property
    def path(self) -> Path | None:
        """The file being shown, None for none."""

        return self._path

    def warm_up(self):
        """The process started ahead of the first file shown, which would
        otherwise wait for it to start."""

        self._connection()

    def is_readable(self, path: Path) -> bool:
        return path not in self._unreadable

    def play(self, path: Path, places: list[float] | None = None) -> bool:
        """The file shown, at the places given, else at random ones; False
        where it cannot be."""

        if path in self._unreadable:
            return False

        conn = self._connection()
        if conn is None:
            return False

        token = next(self._tokens)

        try:
            conn.send(
                (
                    "play",
                    token,
                    str(path),
                    random_places() if places is None else places,
                    SECONDS_EACH,
                )
            )
        except (OSError, ValueError) as e:
            _log.warning(f"Clip preview not asked: {e}")
            return False

        self._token = token
        self._path = path

        return True

    def stop(self):
        if self._token is None:
            return

        self._token = None
        self._path = None

        with self._lock:
            conn = self._conn

        if conn is not None:
            with contextlib.suppress(OSError, ValueError):
                conn.send(("stop",))

    def close(self):
        self._token = None
        self._path = None

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
                target=serve, args=(child_conn,), name="ClipPreview", daemon=True
            )

            try:
                process.start()
            except OSError as e:
                _log.warning(f"Clip preview process not started: {e}")
                return None
            finally:
                child_conn.close()

            self._process, self._conn = process, conn

        threading.Thread(
            target=self._read_answers, args=(conn,), name="ClipPreview", daemon=True
        ).start()

        return conn

    def _read_answers(self, conn):
        while True:
            try:
                answer = conn.recv()
            except (EOFError, OSError):
                break

            self._answer.emit(answer)

        self._answer.emit(("gone", conn))

    def _on_answer(self, answer):
        kind = answer[0]

        if kind == "gone":
            self._process_gone(answer[1])
            return

        token = answer[1]

        # one for a file shown before
        if token != self._token:
            return

        if kind == "failed":
            self._give_up()
            return

        _, _, width, height, data = answer
        image = QImage(data, width, height, width * 4, QImage.Format_RGB32)
        self.frame.emit(image.copy())

    def _process_gone(self, conn):
        with self._lock:
            if self._conn is not conn:
                # closed on purpose
                return

            self._process = self._conn = None

        _log.warning(f"Clip preview process went down on {self._path}")

        if self._token is not None:
            self._give_up()

    def _give_up(self):
        if self._path is not None:
            self._unreadable.add(self._path)

        self._token = None
        self._path = None

        self.failed.emit()
