"""The video under the mouse in Manage Favourites shown moving: a few
seconds at each of a few places in it, in a box beside it, a moment after
the mouse rests on it; gone as it leaves."""

import random
import time

import pytest
from PyQt5.QtCore import QEvent, QPoint, Qt
from PyQt5.QtGui import QColor, QImage
from PyQt5.QtWidgets import QApplication

from gridplayer.dialogs import favourites as dialogs
from gridplayer.dialogs.favourites import (
    PREVIEW_OFFSET,
    HoverPreview,
    ManageFavouritesDialog,
)
from gridplayer.models.favourites import FavouriteFolder, Favourites
from gridplayer.utils import clip_preview_reader as reader
from gridplayer.utils.clip_preview import MARGIN, random_places
from tests.test_favourites import (
    _tree_item,
    _video,
    undated,  # noqa: F401 (autouse here too)
)


class _FakePreviewer:
    def __init__(self):
        self.played = []
        self.stopped = 0
        self.closed = False
        self.warmed = 0
        self.unreadable = set()

        from PyQt5.QtCore import QObject, pyqtSignal

        class _Signals(QObject):
            frame = pyqtSignal(QImage)
            failed = pyqtSignal()

        self._signals = _Signals()
        self.frame = self._signals.frame
        self.failed = self._signals.failed

    def warm_up(self):
        self.warmed += 1

    def is_readable(self, path):
        return path not in self.unreadable

    def play(self, path, places=None):
        self.played.append(path)
        return True

    def stop(self):
        self.stopped += 1

    def close(self):
        self.closed = True


@pytest.fixture
def previewer(monkeypatch):
    fake = _FakePreviewer()

    def made(dialog):
        if dialog._previewer is None:
            dialog._previewer = fake
            fake.frame.connect(dialog._on_preview_frame)
            fake.failed.connect(dialog.stop_preview)
        return fake

    monkeypatch.setattr(ManageFavouritesDialog, "_clip_previewer", made)
    return fake


@pytest.fixture
def films(tmp_path):
    there = tmp_path / "film.mp4"
    there.write_bytes(b"video")
    other = tmp_path / "other.mp4"
    other.write_bytes(b"video")
    return there, other


@pytest.fixture
def dialog(films):
    there, other = films
    made = ManageFavouritesDialog(
        Favourites(
            [
                _video("Film", path=there),
                FavouriteFolder(name="Folder", items=[_video("Other", path=other)]),
                _video("Gone", path=there.with_name("gone.mp4")),
            ]
        )
    )
    yield made
    made.stop_preview()


def _rest_on(dialog, *path):
    dialog._hovered(_tree_item(dialog, *path))
    dialog._preview_timer.timeout.emit()


def _frame(width=320, height=180):
    image = QImage(width, height, QImage.Format_RGB32)
    image.fill(QColor("red"))
    return image


class TestShown:
    def test_after_the_mouse_rests_on_a_video(self, dialog, previewer, films):
        dialog._hovered(_tree_item(dialog, 0))

        assert previewer.played == []
        assert dialog._preview_timer.isActive()
        assert previewer.warmed == 1

        dialog._preview_timer.timeout.emit()

        assert previewer.played == [films[0]]

    def test_its_frames_in_the_box(self, dialog, previewer):
        _rest_on(dialog, 0)

        previewer.frame.emit(_frame())

        assert dialog._preview.isVisible()
        assert dialog._preview.pixmap().size().width() == 320

    def test_one_within_a_folder(self, dialog, previewer, films):
        _rest_on(dialog, 1, 0)

        assert previewer.played == [films[1]]

    def test_another_rested_on_the_one_before_stops(self, dialog, previewer, films):
        _rest_on(dialog, 0)
        previewer.frame.emit(_frame())

        dialog._hovered(_tree_item(dialog, 1, 0))

        assert previewer.stopped >= 1
        assert not dialog._preview.isVisible()

    def test_the_same_one_again_not_started_again(self, dialog, previewer):
        _rest_on(dialog, 0)

        dialog._hovered(_tree_item(dialog, 0))

        assert len(previewer.played) == 1
        assert not dialog._preview_timer.isActive()


class TestNotShown:
    def test_for_a_folder(self, dialog, previewer):
        _rest_on(dialog, 1)

        assert previewer.played == []

    def test_for_a_file_gone(self, dialog, previewer):
        _rest_on(dialog, 2)

        assert previewer.played == []

    def test_for_one_that_could_not_be_shown_before(self, dialog, previewer, films):
        previewer.unreadable.add(films[0])

        _rest_on(dialog, 0)

        assert previewer.played == []

    def test_while_dragging(self, dialog, previewer, monkeypatch):
        monkeypatch.setattr(
            dialogs.QApplication, "mouseButtons", staticmethod(lambda: Qt.LeftButton)
        )

        _rest_on(dialog, 0)

        assert previewer.played == []


class TestGone:
    @pytest.fixture
    def shown(self, dialog, previewer):
        _rest_on(dialog, 0)
        previewer.frame.emit(_frame())
        return dialog

    @pytest.mark.parametrize(
        "event", [QEvent.Leave, QEvent.MouseButtonPress, QEvent.Wheel]
    )
    def test_as_the_mouse_leaves_clicks_or_scrolls(self, shown, previewer, event):
        shown.eventFilter(shown.tree.viewport(), QEvent(event))

        assert not shown._preview.isVisible()
        assert previewer.stopped >= 1

    def test_onto_a_folder(self, shown, previewer):
        shown._hovered(_tree_item(shown, 1))

        assert not shown._preview.isVisible()

    def test_when_it_cannot_be_shown(self, shown, previewer):
        previewer.failed.emit()

        assert not shown._preview.isVisible()

    def test_a_frame_late_for_one_left_not_shown(self, shown, previewer):
        shown.stop_preview()

        previewer.frame.emit(_frame())

        assert not shown._preview.isVisible()

    def test_closed_with_the_window(self, shown, previewer):
        shown.reject()

        assert previewer.closed
        assert not shown._preview.isVisible()


class TestTheBox:
    def test_by_the_mouse(self):
        box = HoverPreview()
        screen = QApplication.primaryScreen().availableGeometry()
        cursor = screen.topLeft() + QPoint(10, 10)

        from PyQt5.QtGui import QPixmap

        box.show_frame(QPixmap.fromImage(_frame(100, 50)), cursor)

        assert box.pos() == cursor + PREVIEW_OFFSET
        assert box.size().width() == 100
        box.hide()

    def test_flipped_where_the_screen_ends(self):
        box = HoverPreview()
        screen = QApplication.primaryScreen().availableGeometry()
        cursor = screen.bottomRight() - QPoint(5, 5)

        from PyQt5.QtGui import QPixmap

        box.show_frame(QPixmap.fromImage(_frame(100, 50)), cursor)

        assert box.geometry().right() < cursor.x()
        assert box.geometry().bottom() < cursor.y()
        box.hide()

    def test_takes_neither_keys_nor_mouse(self):
        box = HoverPreview()

        assert box.testAttribute(Qt.WA_TransparentForMouseEvents)
        assert box.testAttribute(Qt.WA_ShowWithoutActivating)
        assert box.windowFlags() & Qt.ToolTip == Qt.ToolTip


class TestThePlaces:
    def test_one_in_each_stretch_first_to_last(self):
        places = random_places(4, random.Random(1))

        assert len(places) == 4
        assert places == sorted(places)
        span = (1 - 2 * MARGIN) / 4
        for i, place in enumerate(places):
            assert MARGIN + span * i <= place <= MARGIN + span * (i + 1)

    def test_clear_of_its_very_start_and_end(self):
        for seed in range(50):
            places = random_places(4, random.Random(seed))
            assert min(places) >= MARGIN
            assert max(places) <= 1 - MARGIN

    def test_different_each_time(self):
        assert random_places() != random_places()


class TestGoingRound:
    """The process's own reckoning of where a file being shown is."""

    def test_round_the_places_once_shown(self, monkeypatch):
        now = [100.0]
        monkeypatch.setattr(reader.time, "monotonic", lambda: now[0])
        playing = reader._Playing("t", [0.1, 0.5, 0.9], 2.0)

        assert not playing.is_due()  # nothing shown yet

        playing.is_shown = True
        assert playing.is_due()
        assert playing.next_place() == 0.1

        now[0] += 1.0
        assert not playing.is_due()

        now[0] += 1.0
        assert playing.is_due()
        assert [playing.next_place(), playing.next_place()] == [0.5, 0.9]
        assert playing.next_place() == 0.1

    def test_how_long_it_has_waited_to_show(self, monkeypatch):
        now = [5.0]
        monkeypatch.setattr(reader.time, "monotonic", lambda: now[0])
        playing = reader._Playing("t", [], 2.0)

        now[0] += 3.0

        assert playing.waited() == 3.0
        assert playing.places == [0.0]


class _Conn:
    """A pipe's end: what it is asked, and what it sends."""

    def __init__(self, asked):
        self.asked = list(asked)
        self.sent = []

    def poll(self, timeout=0.0):
        """As a pipe's: at once with no timeout, for ever with None."""

        if self.asked:
            return True
        if timeout is None:
            # nothing more will come: as the other end gone
            raise EOFError
        time.sleep(min(timeout, 0.01))
        return False

    def recv(self):
        return self.asked.pop(0)

    def send(self, answer):
        self.sent.append(answer)
        if len(self.sent) >= 3:
            self.asked.append(None)


class _Player:
    def __init__(self, frames=True):
        self.played = []
        self.places = []
        self.stopped = 0
        self._frames = frames

    def play(self, path):
        self.played.append(path)

    def go_to(self, place):
        self.places.append(place)

    def stop(self):
        self.stopped += 1

    def take_frame(self):
        return (2, 2, b"\0" * 16) if self._frames else None


class TestTheProcessLoop:
    def test_frames_sent_as_it_plays_from_its_first_place(self):
        conn = _Conn([("play", 7, "/a.mp4", [0.2, 0.6], 2.0)])
        player = _Player()

        reader._loop(conn, player)

        assert player.played == ["/a.mp4"]
        assert player.places[0] == 0.2
        assert [answer[:2] for answer in conn.sent] == [("frame", 7)] * 3

    def test_only_the_last_asked_played(self):
        conn = _Conn(
            [
                ("play", 1, "/a.mp4", [0.5], 2.0),
                ("play", 2, "/b.mp4", [0.5], 2.0),
            ]
        )
        player = _Player()

        reader._loop(conn, player)

        assert player.played == ["/b.mp4"]
        assert {answer[1] for answer in conn.sent} == {2}

    def test_stopped(self):
        conn = _Conn([("play", 1, "/a.mp4", [0.5], 2.0)])
        player = _Player()
        conn.asked.append(("stop",))

        with pytest.raises(EOFError):
            reader._loop(conn, player)

        assert player.stopped == 1

    def test_one_showing_nothing_given_up_on(self, monkeypatch):
        monkeypatch.setattr(reader, "OPEN_TIMEOUT_S", 0.02)
        conn = _Conn([("play", 3, "/broken.mp4", [0.5], 2.0)])
        player = _Player(frames=False)

        with pytest.raises(EOFError):
            reader._loop(conn, player)

        assert conn.sent == [("failed", 3)]
        assert player.stopped == 1
