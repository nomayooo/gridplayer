"""A bookmark renamed where it is shown, as the viewer does it: added with
M, its row in the list over the video double clicked, the new name typed in
the box laid over the row and Enter pressed; no window asking. Escape in a
second one leaves the name as it was."""


def scenario(d):
    from PyQt5.QtCore import QEvent, QPointF, Qt
    from PyQt5.QtGui import QMouseEvent
    from PyQt5.QtTest import QTest
    from PyQt5.QtWidgets import QApplication

    clip = d.media.clips[0]
    d.open(clip)
    a = d.wait_for_cell("a.mp4")
    d.wait_until(lambda: a.is_playable, "plays")
    d.run(a, "active", "set_pause", True)
    d.ctx.active_block = a

    d.run(a, "active", "seek", 5_000)
    d.wait_until(lambda: abs(a.time - 5_000) < 400, "at 5s")
    QTest.keyClick(QApplication.focusWidget() or d.player, Qt.Key_M)
    d.pump()
    d.check("one added", len(a.bookmarks) == 1, a.bookmarks)

    shown = a.overlay.bookmark_list
    d.wait_until(lambda: shown.isVisibleTo(a.overlay), "the list up")
    a.overlay.lay_out_now()

    def double_click_row():
        point = QPointF(20, shown._rows_top() + 2)
        QApplication.sendEvent(
            shown,
            QMouseEvent(
                QEvent.MouseButtonDblClick,
                point,
                Qt.LeftButton,
                Qt.LeftButton,
                Qt.NoModifier,
            ),
        )
        d.pump()
        return a.bookmarker._in_place

    editor = double_click_row()
    d.check("a box to type in", editor is not None and editor.isVisible())
    d.check(
        "over its row",
        editor.geometry().contains(
            shown.mapToGlobal(QPointF(20, shown._rows_top() + 4).toPoint())
        ),
        editor.geometry(),
    )
    d.check(
        "no window asking",
        not [w for w in d.windows() if w is not editor],
        [type(w).__name__ for w in d.windows()],
    )

    QTest.keyClicks(editor, "Kick-off")
    QTest.keyClick(editor, Qt.Key_Return)
    d.pump()
    d.check("renamed", a.bookmarks[0].name == "Kick-off", a.bookmarks)
    d.wait_until(lambda: shown.rows[0][1] == "Kick-off", "the list says so")
    d.shot("renamed", shown)

    editor = double_click_row()
    QTest.keyClicks(editor, "Something else")
    QTest.keyClick(editor, Qt.Key_Escape)
    d.pump()
    d.check("Escape leaves it", a.bookmarks[0].name == "Kick-off", a.bookmarks)
