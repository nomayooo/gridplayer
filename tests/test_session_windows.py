"""The windows open asked for their videos, to save the session: over local
sockets, found by their files, in this process and in another as the other
windows are; and those gone or not answering let go of."""

import json
import subprocess
import sys
import textwrap
import time

import pytest

from gridplayer.utils import session_windows
from gridplayer.utils.session_windows import SessionServer, ask_other_windows


@pytest.fixture
def registry(tmp_path):
    return tmp_path / "windows"


@pytest.fixture
def servers():
    made = []
    yield made
    for server in made:
        server.stop()


def _serve(registry, servers, videos):
    server = SessionServer(provider=lambda: videos, registry_dir=registry)
    assert server.start()
    servers.append(server)
    return server


class TestInThisProcess:
    def test_each_other_one_answers_in_the_order_opened(self, registry, servers):
        own = _serve(registry, servers, [{"name": "mine"}])
        _serve(registry, servers, [{"name": "first"}])
        time.sleep(0.01)
        _serve(registry, servers, [{"name": "second"}, {"name": "third"}])

        answers = ask_other_windows(registry, own.id)

        assert answers == [[{"name": "first"}], [{"name": "second"}, {"name": "third"}]]

    def test_none_others_none(self, registry, servers):
        own = _serve(registry, servers, [{"name": "mine"}])

        assert ask_other_windows(registry, own.id) == []

    def test_one_gone_left_out_and_its_file_let_go(self, registry, servers):
        own = _serve(registry, servers, [])
        gone = registry / "12345-dead.json"
        gone.write_text(
            json.dumps({"server": "gridplayer-session-12345-dead", "started": 1})
        )

        assert ask_other_windows(registry, own.id) == []
        assert not gone.exists()

    def test_stopped_no_longer_found(self, registry, servers):
        own = _serve(registry, servers, [])
        other = _serve(registry, servers, [{"name": "x"}])

        other.stop()

        assert ask_other_windows(registry, own.id) == []

    def test_one_that_fails_to_say_answers_none(self, registry, servers):
        own = _serve(registry, servers, [])

        def broken():
            raise RuntimeError("no videos")

        server = SessionServer(provider=broken, registry_dir=registry)
        assert server.start()
        servers.append(server)

        assert ask_other_windows(registry, own.id) == [[]]

    def test_one_not_answering_in_time_left_out(self, registry, servers, monkeypatch):
        own = _serve(registry, servers, [])
        other = _serve(registry, servers, [{"name": "slow"}])
        # it takes the question and says nothing
        monkeypatch.setattr(other, "_read", lambda _socket: None)

        started = time.monotonic()
        assert ask_other_windows(registry, own.id, timeout_ms=300) == []
        assert time.monotonic() - started < 2


OTHER_WINDOW = textwrap.dedent(
    """
    import sys
    from pathlib import Path

    from PyQt5.QtCore import QCoreApplication, QTimer

    from gridplayer.utils.session_windows import SessionServer

    app = QCoreApplication([])
    server = SessionServer(
        provider=lambda: [{"name": "from the other process"}],
        registry_dir=Path(sys.argv[1]),
    )
    assert server.start()
    print("ready", flush=True)
    QTimer.singleShot(15000, app.quit)
    app.exec_()
    server.stop()
    """
)


def test_another_process_answers(registry, servers, tmp_path):
    script = tmp_path / "other_window.py"
    script.write_text(OTHER_WINDOW)

    other = subprocess.Popen(
        [sys.executable, str(script), str(registry)],
        stdout=subprocess.PIPE,
        text=True,
    )
    try:
        assert other.stdout.readline().strip() == "ready"

        own = _serve(registry, servers, [])

        answers = ask_other_windows(registry, own.id)

        assert answers == [[{"name": "from the other process"}]]
    finally:
        other.kill()
        other.wait()


def test_answered_well_within_the_time_given():
    assert session_windows.ANSWER_TIMEOUT_MS >= 1000
