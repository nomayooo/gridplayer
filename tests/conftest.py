import os
import sys
import time
import traceback
from contextlib import suppress
from threading import Thread
from types import MappingProxyType, SimpleNamespace

import pytest
from PyQt5.QtWidgets import QApplication
from requests.cookies import RequestsCookieJar

from gridplayer.params.static import ProxyMode
from gridplayer.player.managers import bookmarks as bookmarks_manager
from gridplayer.playlist_settings import PlaylistSettings
from gridplayer.settings import default_value
from gridplayer.utils import cache, cookies, network

# Draw nowhere. A widget a test shows is a real window on this desktop
# otherwise, and since the application is held open for the whole run,
# one shown and not closed sits there blank until the run ends -- it is
# never painted, because a test does not spin an event loop for it.
#
# Set to windows, cocoa or xcb to watch a test draw.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

# Talk to no desktop either. On Linux the dark mode check asks the desktop
# portal over the session bus, and where there is a bus with no portal
# answering on it (a login over ssh) every ask waits out the 25 second
# D-Bus timeout, twice. A bus that is not there is given up on at once.
os.environ["DBUS_SESSION_BUS_ADDRESS"] = "unix:path=/nonexistent/gridplayer-tests"

# what a real Streamlink session starts out with, where a test cares what
# a setting cleared again leaves behind
DEFAULT_TIMEOUT_SEC = 20.0

# the network page asking for nothing, which is how it comes out of the box
DEFAULT_NETWORK_SETTINGS = MappingProxyType(
    {
        "network/proxy_mode": ProxyMode.SYSTEM,
        "network/proxy_url": "",
        "network/user_agent": "",
        "network/force_ipv4": False,
        "network/timeout": 0,
        "network/verify_tls": True,
    }
)

# what the test hosts check for before they serve anything
LOGIN_NAME = "SID"
LOGIN_VALUE = "abc"
LOGIN = f"{LOGIN_NAME}={LOGIN_VALUE}"

COOKIE_LIFETIME_SEC = 10000


def _block_parts():
    """A VideoBlock's parts, by the name the block keeps each under."""

    from gridplayer.widgets.video_block_audio import AudioControl
    from gridplayer.widgets.video_block_bookmarker import Bookmarker
    from gridplayer.widgets.video_block_chapters import ChapterControl
    from gridplayer.widgets.video_block_loop import LoopControl
    from gridplayer.widgets.video_block_navigation import NavigationControl
    from gridplayer.widgets.video_block_preview import PreviewControl
    from gridplayer.widgets.video_block_recovery import RecoveryControl
    from gridplayer.widgets.video_block_screenshot import ScreenshotControl
    from gridplayer.widgets.video_block_sponsorblock import SponsorBlockControl
    from gridplayer.widgets.video_block_status import StatusControl
    from gridplayer.widgets.video_block_stream import StreamControl
    from gridplayer.widgets.video_block_subtitles import SubtitleControl
    from gridplayer.widgets.video_block_view import ViewControl

    return {
        "audio": AudioControl,
        "bookmarker": Bookmarker,
        "chapters": ChapterControl,
        "loop": LoopControl,
        "navigation": NavigationControl,
        "preview": PreviewControl,
        "recovery": RecoveryControl,
        "screenshot": ScreenshotControl,
        "sponsorblock": SponsorBlockControl,
        "status": StatusControl,
        "stream": StreamControl,
        "subtitles": SubtitleControl,
        "view": ViewControl,
    }


def is_block_command(command: str) -> bool:
    """Whether a VideoBlock command, "reload" or "chapters.next", is there:
    the block's own, or one of a part of it (see VideoBlockPart)."""

    from gridplayer.widgets.video_block import VideoBlock

    part, _, method = command.rpartition(".")
    owner = VideoBlock if not part else _block_parts().get(part)

    return owner is not None and hasattr(owner, method)


def mock_block_parts(block):
    """Give a stand-in for a VideoBlock, Mock(spec=VideoBlock), its parts:
    the spec has only what the class has, and the block makes its parts as
    it is made."""

    from unittest.mock import Mock

    for name, part in _block_parts().items():
        setattr(block, name, Mock(spec=part))

    return block


class FakeSettings:
    """A page of settings, answering for itself.

    Stands in for the app-wide singleton, which reads the ini the person
    running the tests actually has.
    """

    def __init__(self, values):
        self._values = values

    def get(self, key):
        return self._values[key]

    def sync_get(self, key):
        return self._values[key]


class FakeStreamlinkSession:
    """Enough of a Streamlink session for the settings to land on.

    And for a stream to be built against, which asks it to vet the
    arguments the request will be made with. What it starts out holding
    is what a real one does, so a test can tell a setting being applied
    from a setting being cleared again.
    """

    def __init__(self, headers=None):
        # a urllib3 global on the real thing, so what it was last told is
        # kept here where a test can see it rather than being applied
        self.address_family = None

        self.http = SimpleNamespace(
            headers=dict(headers or {}),
            cookies=RequestsCookieJar(),
            proxies={},
            trust_env=True,
            verify=True,
            timeout=DEFAULT_TIMEOUT_SEC,
            valid_request_args=dict,
            set_address_family=self._set_address_family,
        )

        self.options = {}

    def set_option(self, key, value):
        self.options[key] = value

    def _set_address_family(self, family=None):
        self.address_family = family


@pytest.fixture(scope="session", autouse=True)
def _qapp_session():
    """Hold one QApplication open for the whole run.

    Destroying a QApplication destroys every QObject alive at the time,
    and the settings singleton keeps a QSettings among them. Modules that
    make their own only ever get this one back, so nothing outlives its
    application.
    """

    return QApplication.instance() or QApplication([])


@pytest.fixture(autouse=True)
def _clear_playlist_settings():
    PlaylistSettings().clear()
    yield
    PlaylistSettings().clear()


@pytest.fixture(autouse=True)
def _no_real_cookies(tmp_path, monkeypatch):
    """Keep every test away from the jar the user actually has.

    The resolvers ask the store whether a URL needs a cookie before they
    decide who fetches it, and the store answers out of the app data
    directory unless it is pointed somewhere else. A test that found a
    login there would resolve differently on the machine that has one.
    """

    store = cookies.CookieStore(tmp_path / "cookies.txt")

    monkeypatch.setattr(cookies, "cookie_store", lambda: store)

    return store


@pytest.fixture(autouse=True)
def _no_real_network_settings(monkeypatch):
    """And away from the proxy the user actually has set.

    The same resolvers ask the network page whether VLC can be left to
    fetch a URL, so a proxy configured on this machine would have them
    resolve differently here than on one without.
    """

    monkeypatch.setattr(
        network, "Settings", lambda: FakeSettings(DEFAULT_NETWORK_SETTINGS)
    )


class StoredSettings:
    """Settings kept in a dict of their own, each out of the box until set."""

    def __init__(self):
        self.values = {}

    def get(self, key):
        return self.values.get(key, default_value(key))

    def sync_get(self, key):
        return self.get(key)

    def set(self, key, value):
        self.values[key] = value


@pytest.fixture(autouse=True)
def remembered_bookmarks(monkeypatch):
    """Away from the bookmarks the user's player remembers, and leaving none
    there: each test with its own, none to begin with."""

    stored = StoredSettings()
    monkeypatch.setattr(bookmarks_manager, "Settings", lambda: stored)

    return stored


@pytest.fixture(autouse=True)
def _no_real_cache(tmp_path, monkeypatch):
    """And away from the cache the user has: the Settings dialog measures
    it as it opens, and its Clear button empties it."""

    root = tmp_path / "cache"

    monkeypatch.setattr(cache, "cache_root", lambda: root)

    return root


# how often a serving thread looks up to see whether it has been asked
# to stop. Shutting one down waits for it to notice, so this is what a
# test pays to put its server away, and the default of half a second is
# most of what a suite of them costs.
SHUTDOWN_POLL_SEC = 0.01


@pytest.fixture
def serving():
    """Run servers on their own threads for the length of a test.

    Every proxy test needs at least two of them up at once, and a test
    that leaves one running leaks a thread into the next.
    """

    running = []

    def _serve(server):
        thread = Thread(
            target=server.serve_forever,
            kwargs={"poll_interval": SHUTDOWN_POLL_SEC},
            daemon=True,
        )
        thread.start()

        running.append((server, thread))

        return server

    yield _serve

    for server, thread in running:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


@pytest.fixture
def local_login(_no_real_cookies, monkeypatch):
    """A stored login for 127.0.0.1, where the test hosts live.

    The switches come with it, so a test is not at the mercy of whatever
    the person running it has cookies set to.
    """

    values = {"cookies/enabled": True, "cookies/allow_update": False}

    monkeypatch.setattr(cookies, "Settings", lambda: FakeSettings(values))

    expires = int(time.time()) + COOKIE_LIFETIME_SEC

    _no_real_cookies.save(
        cookies.parse_cookies(
            "# Netscape HTTP Cookie File\n"
            f"127.0.0.1\tFALSE\t/\tFALSE\t{expires}\t{LOGIN_NAME}\t{LOGIN_VALUE}\n"
        )
    )

    return values


@pytest.fixture(autouse=True)
def _slot_exceptions_fail_the_test(monkeypatch):
    """An exception raised inside a Qt slot made a failure of the test it
    came in, with its traceback, rather than ending the whole run: PyQt
    aborts on one only when the hook is Python's own."""

    raised = []

    monkeypatch.setattr(
        sys, "excepthook", lambda kind, value, tb: raised.append((kind, value, tb))
    )

    yield

    if raised:
        kind, value, tb = raised[0]
        pytest.fail(
            "Raised inside a Qt slot:\n"
            + "".join(traceback.format_exception(kind, value, tb)),
            pytrace=False,
        )


@pytest.fixture(autouse=True)
def _playlist_title_timers_stopped(monkeypatch):
    """Each playlist manager a test makes has its window title kept up to
    date by a timer once its playlist is saved: stopped with the test, not
    left to tick into a later one, whose stand-in context it then reads."""

    from gridplayer.player.managers.playlist import PlaylistManager

    made = []
    real_init = PlaylistManager.__init__

    def init(self, *args, **kwargs):
        real_init(self, *args, **kwargs)
        made.append(self)

    monkeypatch.setattr(PlaylistManager, "__init__", init)

    yield

    for manager in made:
        # one whose C++ side is gone already has no timer left
        with suppress(RuntimeError):
            manager._title_timer.stop()
