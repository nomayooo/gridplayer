"""The bookmarks as a short list in a corner of the cell: none there with
none, up once there are some, each a row to click to go there, the one the
video last passed picked out, more than it shows a turn of the wheel away,
moved to another corner from the menu, hidden and shown again with Shift+M
and with its button on the bar, and none in a cell too small to spare the
room."""


def _at(d, a, ms, what):
    d.run(a, "active", "seek", ms)
    d.wait_until(lambda: abs(a.time - ms) < 400, what)


def scenario(d):
    from PyQt5.QtCore import QPoint, Qt
    from PyQt5.QtTest import QTest

    from gridplayer.models.bookmark import Bookmark
    from gridplayer.widgets import video_overlay_bookmark_list as list_module

    clip = d.media.clips[0]
    d.open(clip)
    a = d.wait_for_cell("a.mp4")
    d.wait_until(lambda: a.is_playable, "plays")
    d.run(a, "active", "set_pause", True)
    d.ctx.active_block = a

    shown = a.overlay.bookmark_list
    d.check("none with none", not shown.isVisibleTo(a.overlay))

    d.ctx.bookmarks.set(
        a.video_params.uri,
        a.video_params.id,
        [
            Bookmark(time_ms=2_000, name="Intro"),
            Bookmark(time_ms=7_000, name="Goal", color="#18ffff"),
            Bookmark(time_ms=13_000, name="A rather long name for the ending"),
        ],
    )
    d.pump()
    d.wait_until(lambda: shown.isVisibleTo(a.overlay), "up with some")
    d.check("three rows", len(shown.rows) == 3, shown.rows)

    _at(d, a, 9_000, "at 9s")
    d.pump()
    d.check("the one last passed picked out", shown.current_row == 1, shown.current_row)
    d.check(
        "no wider than its share",
        shown.width()
        <= list_module.OverlayBookmarkList.max_width_in(a.overlay.width()),
        (shown.width(), a.overlay.width()),
    )
    d.shot("cell", a)
    d.shot("list", shown)

    # the third row clicked
    row_height = shown.height() // 3
    QTest.mouseClick(
        shown, Qt.LeftButton, Qt.NoModifier, QPoint(20, row_height * 2 + 3)
    )
    d.wait_until(lambda: abs(a.time - 13_000) < 400, "gone to the third")
    d.check("still paused", a.video_params.is_paused)

    # more than it shows: the rest a turn of the wheel away
    many = [Bookmark(time_ms=1_000 * i, name=f"B{i}") for i in range(1, 9)]
    d.ctx.bookmarks.set(a.video_params.uri, a.video_params.id, many)
    d.pump()
    d.check(
        "five shown",
        len(shown.shown_rows) == list_module.MAX_ROWS,
        list(shown.shown_rows),
    )
    from PyQt5.QtCore import QPointF
    from PyQt5.QtGui import QWheelEvent
    from PyQt5.QtWidgets import QApplication

    event = QWheelEvent(
        QPointF(20, 20),
        QPointF(shown.mapToGlobal(QPoint(20, 20))),
        QPoint(0, 0),
        QPoint(0, -120),
        Qt.NoButton,
        Qt.NoModifier,
        Qt.NoScrollPhase,
        False,
    )
    QApplication.sendEvent(shown, event)
    d.check("scrolled down one", shown.shown_rows.start == 1, list(shown.shown_rows))
    d.shot("many", shown)

    # moved from the menu, to the bottom right: there, and in a cell opened
    # after too; and off
    d.act(a, "Bookmark List Bottom Right")
    a.overlay.lay_out_now()
    d.pump()
    middle = shown.geometry().center()
    d.check(
        "bottom right",
        middle.x() > a.overlay.width() / 2 and middle.y() > a.overlay.height() / 2,
        (middle.x(), middle.y(), a.overlay.width(), a.overlay.height()),
    )
    d.shot("bottom right", a)

    d.open(d.media.clips[1])
    b = d.wait_for_cell("b.mp4")
    d.check(
        "a cell opened after too",
        b.overlay.bookmark_list_position == a.overlay.bookmark_list_position,
        str(b.overlay.bookmark_list_position),
    )
    d.act(b, "Close")
    d.wait_until(lambda: len(d.cells) == 1, "only a left")
    d.ctx.active_block = a

    d.act(a, "Bookmark List Top Left")

    # hidden and shown again with Shift+M, as the viewer presses it, and by
    # the button on the bar, filled while it is shown
    button = a.overlay.bookmark_list_button
    d.check("its button there", button.isVisibleTo(a.overlay) and not button.is_off)

    from PyQt5.QtWidgets import QApplication

    QTest.keyClick(QApplication.focusWidget() or d.player, Qt.Key_M, Qt.ShiftModifier)
    d.pump()
    d.check("hidden with Shift+M", not shown.isVisibleTo(a.overlay))
    d.check(
        "the button there still, empty", button.isVisibleTo(a.overlay) and button.is_off
    )
    d.shot("hidden", a)

    QTest.mouseClick(button, Qt.LeftButton)
    d.pump()
    d.check("shown by the button", shown.isVisibleTo(a.overlay))
    d.check(
        "in its corner still", shown.geometry().center().x() < a.overlay.width() / 2
    )

    # a cell too small
    d.player.resize(260, 200)
    d.wait_until(lambda: a.overlay.width() < 280, "a narrow cell")
    d.check("none in a small cell", not shown.isVisibleTo(a.overlay), a.overlay.size())
