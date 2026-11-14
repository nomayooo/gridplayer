"""The bookmarks as a short list in a corner of the cell: what it lists, the
one it picks out, a row clicked and the wheel turned over it, and when it is
there at all."""

import pytest
from PyQt5.QtCore import QPoint, QPointF, Qt
from PyQt5.QtGui import QFontMetrics, QWheelEvent
from PyQt5.QtTest import QTest
from PyQt5.QtWidgets import QApplication

from gridplayer.models.seek_mark import SeekMark, SeekMarkKind
from gridplayer.widgets.video_overlay import OverlayBlock, OverlayMode
from gridplayer.widgets.video_overlay_bookmark_list import (
    MAX_ROWS,
    MIN_CELL_HEIGHT,
    MIN_CELL_WIDTH,
    OverlayBookmarkList,
)
from gridplayer.widgets.video_overlay_elements import BOOKMARK_COLOR

LENGTH = 60000


def _bookmark(time_ms, name, color=None):
    return SeekMark(time_ms, name, SeekMarkKind.BOOKMARK, color=color)


MARKS = (
    SeekMark(1000, "A chapter"),
    _bookmark(30000, "Goal", "#18ffff"),
    _bookmark(10000, "Intro"),
)


@pytest.fixture
def overlay():
    overlay = OverlayBlock()
    overlay.setAttribute(Qt.WA_DontShowOnScreen)
    overlay.resize(640, 360)
    overlay.set_color("#ffffff")
    overlay.set_position(20000, LENGTH)
    overlay.show()

    yield overlay

    overlay.close()


@pytest.fixture
def shown(overlay):
    overlay.set_seek_marks(MARKS)
    overlay.lay_out_now()
    return overlay.bookmark_list


def _row_point(shown, row):
    return QPoint(20, shown._rows_top() + shown._row_height() * row + 2)


def _wheel(widget, down=True):
    event = QWheelEvent(
        QPointF(20, 20),
        QPointF(widget.mapToGlobal(QPoint(20, 20))),
        QPoint(0, 0),
        QPoint(0, -120 if down else 120),
        Qt.NoButton,
        Qt.NoModifier,
        Qt.NoScrollPhase,
        False,
    )
    QApplication.sendEvent(widget, event)
    return event


class TestWhatItLists:
    def test_the_bookmarks_alone_first_to_last(self, shown):
        assert shown.rows == [
            (10000, "Intro", BOOKMARK_COLOR),
            (30000, "Goal", "#18ffff"),
        ]

    def test_none_without_bookmarks(self, overlay):
        overlay.set_seek_marks((SeekMark(1000, "A chapter"),))

        assert not overlay.bookmark_list.isVisibleTo(overlay)

    def test_up_with_some(self, shown, overlay):
        assert shown.isVisibleTo(overlay)

    def test_the_one_last_passed_picked_out(self, shown, overlay):
        assert shown.current_row == 0

        overlay.set_position(35000, LENGTH)
        assert shown.current_row == 1

        overlay.set_position(5000, LENGTH)
        assert shown.current_row is None

    def test_wide_enough_for_each_name_in_bold(self, shown):
        font = shown.font()
        font.setBold(True)

        assert shown.sizeHint().width() > QFontMetrics(font).horizontalAdvance("Intro")


class TestPicked:
    def test_a_row_clicked_says_its_bookmark(self, shown):
        picked = []
        shown.bookmark_clicked.connect(picked.append)

        QTest.mouseClick(shown, Qt.LeftButton, Qt.NoModifier, _row_point(shown, 1))

        assert picked == [(30000,)]

    def test_said_on_as_a_marker_clicked_is(self, shown, overlay):
        picked = []
        overlay.bookmark_clicked.connect(picked.append)

        QTest.mouseClick(shown, Qt.LeftButton, Qt.NoModifier, _row_point(shown, 0))

        assert picked == [(10000,)]

    def test_nothing_for_another_button(self, shown):
        picked = []
        shown.bookmark_clicked.connect(picked.append)

        QTest.mouseClick(shown, Qt.RightButton, Qt.NoModifier, _row_point(shown, 0))

        assert picked == []

    def test_a_press_on_it_is_the_overlays_own(self, shown, overlay):
        """Not the cell's, which a click on the picture pauses."""

        point = shown.mapToGlobal(_row_point(shown, 0))

        assert overlay.is_control_at(point)


class TestMoreThanItShows:
    @pytest.fixture
    def many(self, overlay):
        overlay.set_seek_marks(
            tuple(_bookmark(1000 * i, f"B{i}") for i in range(1, MAX_ROWS + 4))
        )
        overlay.lay_out_now()
        return overlay.bookmark_list

    def test_only_so_many_shown(self, many):
        assert list(many.shown_rows) == list(range(MAX_ROWS))

    def test_the_wheel_goes_down_and_back(self, many):
        _wheel(many)
        assert many.shown_rows.start == 1

        _wheel(many, down=False)
        assert many.shown_rows.start == 0

    def test_no_further_than_the_last(self, many):
        for _ in range(20):
            _wheel(many)

        assert many.shown_rows.stop == len(many.rows)

    def test_a_row_clicked_after_scrolling_is_that_one(self, many):
        _wheel(many)
        picked = []
        many.bookmark_clicked.connect(picked.append)

        QTest.mouseClick(many, Qt.LeftButton, Qt.NoModifier, _row_point(many, 0))

        assert picked == [(2000,)]

    def test_with_few_the_wheel_is_the_cells(self, shown):
        assert not _wheel(shown).isAccepted()


class TestKeptOutOfTheWay:
    def test_no_wider_than_its_share_of_the_cell(self, overlay):
        overlay.set_seek_marks((_bookmark(1000, "A name " * 20),))
        overlay.lay_out_now()

        shown = overlay.bookmark_list
        assert shown.width() <= OverlayBookmarkList.max_width_in(overlay.width())

    @pytest.mark.parametrize(
        "size",
        [(MIN_CELL_WIDTH - 1, 400), (640, MIN_CELL_HEIGHT - 1)],
        ids=["narrow", "short"],
    )
    def test_none_in_a_small_cell(self, shown, overlay, size):
        overlay.resize(*size)

        assert not shown.isVisibleTo(overlay)

        overlay.resize(640, 360)
        assert shown.isVisibleTo(overlay)

    @pytest.mark.parametrize(
        "mode", [OverlayMode.LOADING, OverlayMode.STOPPED, OverlayMode.ERROR]
    )
    def test_none_over_a_cell_with_no_picture(self, shown, overlay, mode):
        overlay.set_mode(mode)

        assert not shown.isVisibleTo(overlay)

    def test_gone_with_the_rest_of_the_overlay(self, shown, overlay):
        overlay.set_is_chrome_visible(False)

        assert not shown.isVisible()

    def test_smaller_than_the_rest_of_the_overlay(self, shown, overlay):
        assert shown.font().pointSizeF() < overlay.label_text.font().pointSizeF()
