"""The bookmarks as a short list in a corner of the cell: what it lists, the
one it picks out, a row clicked and the wheel turned over it, and when it is
there at all."""

import pytest
from PyQt5.QtCore import QEvent, QPoint, QPointF, Qt
from PyQt5.QtGui import QFontMetrics, QMouseEvent, QWheelEvent
from PyQt5.QtTest import QTest
from PyQt5.QtWidgets import QApplication

from gridplayer.models.seek_mark import SeekMark, SeekMarkKind
from gridplayer.params.static import BookmarkListPosition
from gridplayer.widgets.video_overlay import OverlayBlock, OverlayMode
from gridplayer.widgets.video_overlay_bookmark_list import (
    MAX_ROWS,
    MIN_CELL_HEIGHT,
    MIN_CELL_WIDTH,
    MIN_RENAME_WIDTH,
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


class TestWhereItGoes:
    def test_top_left_to_begin_with(self, shown, overlay):
        assert overlay.bookmark_list_position is BookmarkListPosition.TOP_LEFT
        assert shown.x() < overlay.width() / 2
        assert shown.y() < overlay.height() / 2

    @pytest.mark.parametrize(
        ("position", "is_left", "is_top"),
        [
            (BookmarkListPosition.TOP_LEFT, True, True),
            (BookmarkListPosition.TOP_RIGHT, False, True),
            (BookmarkListPosition.BOTTOM_LEFT, True, False),
            (BookmarkListPosition.BOTTOM_RIGHT, False, False),
        ],
    )
    def test_in_the_corner_picked(self, shown, overlay, position, is_left, is_top):
        overlay.set_bookmark_list_position(position)
        overlay.lay_out_now()

        middle = shown.geometry().center()
        assert (middle.x() < overlay.width() / 2) == is_left
        assert (middle.y() < overlay.height() / 2) == is_top
        assert shown.isVisibleTo(overlay)

    def test_on_the_right_clear_of_the_volumes_bar(self, shown, overlay):
        overlay.set_bookmark_list_position(BookmarkListPosition.TOP_RIGHT)
        overlay.lay_out_now()

        volume = overlay.volume_bar
        if volume.isVisibleTo(overlay):
            assert not shown.geometry().intersects(volume.geometry())

    def test_above_the_bar_at_the_bottom(self, shown, overlay):
        overlay.set_bookmark_list_position(BookmarkListPosition.BOTTOM_LEFT)
        overlay.lay_out_now()

        bar_top = overlay.progress_bar.mapTo(
            overlay, overlay.progress_bar.rect().topLeft()
        )
        assert shown.mapTo(overlay, shown.rect().bottomLeft()).y() < bar_top.y()


class TestShownOrNot:
    def test_shown_to_begin_with(self, shown, overlay):
        assert overlay.is_bookmark_list_shown
        assert shown.isVisibleTo(overlay)

    def test_hidden_and_shown_again_where_it_was(self, shown, overlay):
        overlay.set_bookmark_list_position(BookmarkListPosition.BOTTOM_RIGHT)

        overlay.set_bookmark_list_shown(False)
        assert not shown.isVisibleTo(overlay)

        overlay.set_bookmark_list_shown(True)
        overlay.lay_out_now()
        assert shown.isVisibleTo(overlay)
        assert overlay.bookmark_list_position is BookmarkListPosition.BOTTOM_RIGHT


class TestItsButton:
    def test_there_with_bookmarks(self, shown, overlay):
        assert overlay.bookmark_list_button.isVisibleTo(overlay)

    def test_none_without(self, overlay):
        overlay.set_seek_marks((SeekMark(1000, "A chapter"),))

        assert not overlay.bookmark_list_button.isVisibleTo(overlay)

    def test_there_with_the_list_hidden_to_show_it_again(self, shown, overlay):
        overlay.set_bookmark_list_shown(False)

        button = overlay.bookmark_list_button
        assert button.isVisibleTo(overlay)
        assert button.is_off

        overlay.set_bookmark_list_shown(True)
        assert not button.is_off

    def test_none_where_the_list_has_no_room(self, shown, overlay):
        overlay.resize(MIN_CELL_WIDTH - 1, 400)

        assert not overlay.bookmark_list_button.isVisibleTo(overlay)

    def test_none_over_a_cell_with_no_picture(self, shown, overlay):
        overlay.set_mode(OverlayMode.LOADING)

        assert not overlay.bookmark_list_button.isVisibleTo(overlay)

    def test_clicked_asks_for_it_shown_or_not(self, shown, overlay):
        asked = []
        overlay.bookmark_list_toggle_clicked.connect(lambda: asked.append(True))

        QTest.mouseClick(overlay.bookmark_list_button, Qt.LeftButton)

        assert asked == [True]

    def test_in_the_bar_after_the_time(self, shown, overlay):
        bar = overlay.bottom_bar
        widgets = [bar.itemAt(i).widget() for i in range(bar.count())]

        assert widgets.index(overlay.bookmark_list_button) == (
            widgets.index(overlay.label_progress) + 1
        )


def _delete_point(shown, row):
    top = shown._rows_top() + shown._row_height() * row
    return shown._delete_rect(top).center().toPoint()


class TestDeletingOne:
    def test_the_cross_on_the_row_under_the_mouse(self, shown):
        # sent as it is: QTest.mouseMove moves nothing with no button held
        QApplication.sendEvent(
            shown,
            QMouseEvent(
                QEvent.MouseMove,
                QPointF(_row_point(shown, 1)),
                Qt.NoButton,
                Qt.NoButton,
                Qt.NoModifier,
            ),
        )

        assert shown._hovered == 1
        assert shown.is_delete_at(_delete_point(shown, 1))
        assert not shown.is_delete_at(_row_point(shown, 1))

    def test_clicked_says_which_to_delete_not_where_to_go(self, shown):
        deleted, gone_to = [], []
        shown.bookmark_remove_clicked.connect(deleted.append)
        shown.bookmark_clicked.connect(gone_to.append)

        QTest.mouseClick(shown, Qt.LeftButton, Qt.NoModifier, _delete_point(shown, 1))

        assert (deleted, gone_to) == ([30000], [])

    def test_the_rest_of_the_row_still_goes_there(self, shown):
        deleted, gone_to = [], []
        shown.bookmark_remove_clicked.connect(deleted.append)
        shown.bookmark_clicked.connect(gone_to.append)

        QTest.mouseClick(shown, Qt.LeftButton, Qt.NoModifier, _row_point(shown, 1))

        assert (deleted, gone_to) == ([], [(30000,)])

    def test_said_on_by_the_overlay(self, shown, overlay):
        deleted = []
        overlay.bookmark_remove_clicked.connect(deleted.append)

        QTest.mouseClick(shown, Qt.LeftButton, Qt.NoModifier, _delete_point(shown, 0))

        assert deleted == [10000]


def test_each_name_shown_whole_where_there_is_room(overlay):
    """Not cut short at the width it was given for itself."""

    overlay.set_seek_marks(
        tuple(_bookmark(1000 * i, f"Bookmark {i}") for i in range(1, 4))
    )
    overlay.lay_out_now()

    shown = overlay.bookmark_list
    font = shown.font()
    font.setBold(True)
    metrics = QFontMetrics(font)

    time_width = max(
        metrics.horizontalAdvance(shown._time_txt(t)) for t, *_ in shown.rows
    )
    name_width = shown.width() - (6 + 6 + 6) - 6 * 2 - time_width - 6

    # more than just its width: Qt cuts one given that alone short
    longest = max(metrics.horizontalAdvance(name) for _, name, _ in shown.rows)
    assert name_width > longest


def _double_click(widget, point, button=Qt.LeftButton):
    QApplication.sendEvent(
        widget,
        QMouseEvent(
            QEvent.MouseButtonDblClick,
            QPointF(point),
            button,
            button,
            Qt.NoModifier,
        ),
    )


class TestRenamingInPlace:
    def test_a_row_double_clicked_asks_for_its_name(self, shown):
        asked = []
        shown.bookmark_rename_requested.connect(
            lambda time_ms, rect: asked.append((time_ms, rect))
        )

        _double_click(shown, _row_point(shown, 1))

        assert [time_ms for time_ms, _ in asked] == [30000]
        rect = asked[0][1]
        row_on_screen = shown.mapToGlobal(_row_point(shown, 1))
        assert rect.top() <= row_on_screen.y() <= rect.bottom()
        assert rect.width() >= MIN_RENAME_WIDTH

    def test_not_on_its_cross(self, shown):
        asked = []
        shown.bookmark_rename_requested.connect(lambda *args: asked.append(args))

        _double_click(shown, _delete_point(shown, 0))

        assert asked == []

    def test_not_with_another_button(self, shown):
        asked = []
        shown.bookmark_rename_requested.connect(lambda *args: asked.append(args))

        _double_click(shown, _row_point(shown, 0), Qt.RightButton)

        assert asked == []

    def test_passed_on_by_the_overlay(self, overlay, shown):
        asked = []
        overlay.bookmark_rename_requested.connect(
            lambda time_ms, _rect: asked.append(time_ms)
        )

        _double_click(shown, _row_point(shown, 0))

        assert asked == [10000]
