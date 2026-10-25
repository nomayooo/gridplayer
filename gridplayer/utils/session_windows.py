"""The windows of GridPlayer open at once, each asked by another for the
videos it plays, to save the session they make together.

Each window serves its own over a local socket of its own, for the user
alone, and is found by a file of its own in the app's data folder while it
is open: what the socket is called and when the window started. A file
left by a window that is gone is let go of when nothing answers at it.
"""

import json
import logging
import os
import time
from pathlib import Path
from uuid import uuid4

from PyQt5.QtCore import QEventLoop, QObject, QTimer
from PyQt5.QtNetwork import QLocalServer, QLocalSocket

_log = logging.getLogger(__name__)

REQUEST = b"session-videos\n"

# how long the others are given to answer, all together
ANSWER_TIMEOUT_MS = 3000


class SessionServer(QObject):
    """This window's videos, given to any other that asks: provider() makes
    them, a list of what JSON can carry."""

    def __init__(self, provider, registry_dir: Path, parent=None):
        super().__init__(parent)

        self._provider = provider
        self._registry_dir = registry_dir

        self.id = f"{os.getpid()}-{uuid4().hex[:8]}"
        self.started = time.time()

        self._name = f"gridplayer-session-{self.id}"
        self._file = registry_dir / f"{self.id}.json"

        self._server = QLocalServer(self)
        self._server.setSocketOptions(QLocalServer.UserAccessOption)
        self._server.newConnection.connect(self._take_connections)

        self._asked: dict = {}

    def start(self) -> bool:
        QLocalServer.removeServer(self._name)

        if not self._server.listen(self._name):
            _log.warning(f"Session server not started: {self._server.errorString()}")
            return False

        try:
            self._registry_dir.mkdir(parents=True, exist_ok=True)
            self._file.write_text(
                json.dumps({"server": self._name, "started": self.started}),
                encoding="utf-8",
            )
        except OSError as e:
            _log.warning(f"Session server not made known: {e}")
            self._server.close()
            return False

        return True

    def stop(self):
        self._server.close()
        self._file.unlink(missing_ok=True)

    def _take_connections(self):
        while (socket := self._server.nextPendingConnection()) is not None:
            self._asked[socket] = bytearray()
            socket.readyRead.connect(lambda s=socket: self._read(s))
            socket.disconnected.connect(lambda s=socket: self._let_go(s))

    def _let_go(self, socket):
        self._asked.pop(socket, None)
        socket.deleteLater()

    def _read(self, socket):
        asked = self._asked.get(socket)
        if asked is None:
            return

        asked.extend(bytes(socket.readAll()))

        if b"\n" not in asked:
            return

        # in a Qt slot: nothing let out of it
        try:
            videos = self._provider()
        except Exception:
            _log.exception("Session videos not made")
            videos = []

        socket.write(json.dumps(videos).encode("utf-8") + b"\n")
        socket.flush()
        socket.disconnectFromServer()


def ask_other_windows(
    registry_dir: Path, own_id: str, timeout_ms: int = ANSWER_TIMEOUT_MS
) -> list[list]:
    """The videos of each other window open, in the order they were opened;
    one that does not answer in time left out."""

    windows = []

    for file in sorted(registry_dir.glob("*.json")):
        if file.stem == own_id:
            continue

        try:
            info = json.loads(file.read_text(encoding="utf-8"))
            windows.append((file, info["server"], float(info["started"])))
        except (OSError, ValueError, KeyError, TypeError):
            continue

    if not windows:
        return []

    loop = QEventLoop()
    answers: dict[Path, list] = {}
    pending = set()
    sockets = []

    def done(file):
        pending.discard(file)
        if not pending:
            loop.quit()

    for file, server, _ in windows:
        socket = QLocalSocket()
        sockets.append(socket)
        pending.add(file)
        answer = bytearray()

        def read(socket=socket, answer=answer, file=file):
            answer.extend(bytes(socket.readAll()))
            if b"\n" not in answer:
                return
            try:
                answers[file] = json.loads(bytes(answer).split(b"\n", 1)[0])
            except ValueError:
                _log.warning(f"Session window answered nonsense: {file.stem}")
            done(file)

        def failed(error, file=file):
            # a window gone, its file left behind
            if error in (
                QLocalSocket.ServerNotFoundError,
                QLocalSocket.ConnectionRefusedError,
            ):
                file.unlink(missing_ok=True)
            if file not in answers:
                done(file)

        socket.connected.connect(lambda socket=socket: socket.write(REQUEST))
        socket.readyRead.connect(read)
        socket.errorOccurred.connect(failed)
        socket.connectToServer(server)

    if pending:
        QTimer.singleShot(timeout_ms, loop.quit)
        loop.exec_()

    for socket in sockets:
        socket.abort()

    return [
        answers[file]
        for file, _, _ in sorted(windows, key=lambda window: window[2])
        if file in answers
    ]
