"""The windows of GridPlayer open at once, each asked by another for the
videos it plays, to save the session they make together.

Each window serves its own on a connection of its own (a named pipe on
Windows, a socket file elsewhere), as the single instance listener takes
files for the window open (see gridplayer.utils.single_instance): for the
user alone, with a key only the user's files know. It is found by a file
of its own in the app's data folder while it is open: where it listens,
with the key, and when it started. A file left by a window that is gone is
let go of when nothing answers at it.

The videos are made where the window's are, on the GUI thread, the server
waiting for them on its own; and the window asking keeps its own events
going while it waits, for one in the same process to answer.
"""

import json
import logging
import os
import secrets
import tempfile
import threading
import time
from multiprocessing import connection
from pathlib import Path
from uuid import uuid4

from PyQt5.QtCore import QCoreApplication, QObject, pyqtSignal

from gridplayer.params import env

_log = logging.getLogger(__name__)

REQUEST = "session-videos"
_STOP = "stop"

# how long the others are given to answer, all together
ANSWER_TIMEOUT_MS = 3000

# how long a window's own are waited for on its GUI thread
_MAKE_TIMEOUT_S = 2.0


def _address(window_id: str) -> tuple[str, str]:
    if env.IS_WINDOWS:
        return rf"\\.\pipe\gridplayer-session-{window_id}", "AF_PIPE"

    # short, as a socket's path has to be
    return str(Path(tempfile.gettempdir()) / f"gp-session-{window_id}"), "AF_UNIX"


class _Asked:
    """One question waiting for its answer from the GUI thread."""

    def __init__(self):
        self.videos: list = []
        self.answered = threading.Event()


class SessionServer(QObject):
    """This window's videos, given to any other that asks: provider() makes
    them, on the GUI thread, a list of what JSON can carry."""

    _asked = pyqtSignal(object)

    def __init__(self, provider, registry_dir: Path, parent=None):
        super().__init__(parent)

        self._provider = provider
        self._registry_dir = registry_dir

        self.id = f"{os.getpid()}-{uuid4().hex[:8]}"
        self.started = time.time()

        self._address, self._family = _address(self.id)
        self._key = secrets.token_bytes(16)
        self._file = registry_dir / f"{self.id}.json"

        self._listener = None
        self._thread = None

        # queued to the thread this lives on, the GUI one
        self._asked.connect(self._answer)

    def start(self) -> bool:
        try:
            self._listener = connection.Listener(
                self._address, self._family, authkey=self._key
            )
        except OSError as e:
            _log.warning(f"Session server not started: {e}")
            return False

        try:
            self._registry_dir.mkdir(parents=True, exist_ok=True)
            self._file.write_text(
                json.dumps(
                    {
                        "address": self._address,
                        "family": self._family,
                        "key": self._key.hex(),
                        "started": self.started,
                    }
                ),
                encoding="utf-8",
            )
        except OSError as e:
            _log.warning(f"Session server not made known: {e}")
            self._listener.close()
            self._listener = None
            return False

        self._thread = threading.Thread(
            target=self._serve, name="SessionServer", daemon=True
        )
        self._thread.start()

        return True

    def stop(self):
        self._file.unlink(missing_ok=True)

        if self._thread is None or not self._thread.is_alive():
            return

        # waiting for one to ask, on a pipe nothing else would wake it from
        try:
            with connection.Client(
                self._address, self._family, authkey=self._key
            ) as client:
                client.send(_STOP)
        except OSError as e:
            _log.debug(f"Session server not told to stop: {e}")

        self._thread.join(timeout=2)

    def _serve(self):
        listener = self._listener

        try:
            while True:
                try:
                    client = listener.accept()
                except connection.AuthenticationError:
                    continue
                except OSError:
                    break

                with client:
                    try:
                        request = client.recv()
                    except (EOFError, OSError):
                        continue

                    if request == _STOP:
                        break

                    if request != REQUEST:
                        continue

                    asked = _Asked()
                    self._asked.emit(asked)
                    asked.answered.wait(_MAKE_TIMEOUT_S)

                    try:
                        client.send(json.dumps(asked.videos))
                    except OSError:
                        continue
        finally:
            listener.close()

    def _answer(self, asked: _Asked):
        # in a Qt slot: nothing let out of it
        try:
            asked.videos = self._provider()
        except Exception:
            _log.exception("Session videos not made")
            asked.videos = []

        asked.answered.set()


def ask_other_windows(
    registry_dir: Path, own_id: str, timeout_ms: int = ANSWER_TIMEOUT_MS
) -> list[list]:
    """The videos of each other window open, in the order they were opened;
    one that does not answer in time left out."""

    deadline = time.monotonic() + timeout_ms / 1000
    windows = []

    for file in sorted(registry_dir.glob("*.json")):
        if file.stem == own_id:
            continue

        try:
            info = json.loads(file.read_text(encoding="utf-8"))
            windows.append(
                (
                    float(info["started"]),
                    file,
                    info["address"],
                    info["family"],
                    bytes.fromhex(info["key"]),
                )
            )
        except (OSError, ValueError, KeyError, TypeError):
            continue

    asking = []

    for started, file, address, family, key in sorted(windows):
        try:
            client = connection.Client(address, family, authkey=key)
            client.send(REQUEST)
        except (FileNotFoundError, ConnectionRefusedError):
            # a window gone, its file left behind
            file.unlink(missing_ok=True)
            continue
        except (OSError, EOFError, connection.AuthenticationError) as e:
            _log.warning(f"Session window not asked: {file.stem}: {e}")
            continue

        asking.append((started, client))

    answers = []

    for _, client in asking:
        with client:
            answer = _wait_for_answer(client, deadline)

        if answer is not None:
            answers.append(answer)

    return answers


def _wait_for_answer(client, deadline: float):
    # the GUI thread kept going, for a window of this process to answer
    while not client.poll(0.02):
        QCoreApplication.processEvents()
        if time.monotonic() > deadline:
            return None

    try:
        return json.loads(client.recv())
    except (EOFError, OSError, ValueError):
        return None
