"""Bookmarks taken back and deleted, as the viewer does it: three added with
M, the last of them taken back with Ctrl+M, then another deleted from the
list over the video with the cross its row shows under the mouse, without
being asked."""


def _press(d, key, modifiers=None):
    from PyQt5.QtCore import Qt
    from PyQt5.QtTest import QTest
    from PyQt5.QtWidgets import QApplication

    QTest.keyClick(
        QApplication.focusWidget() or d.player, key, modifiers or Qt.NoModifier
    )
    d.pump()


def _at(d, a, ms, what):
    d.run(a, "active", "seek", ms)
    d.wait_until(lambda: abs(a.time - ms) < 400, what)


def scenario(d):
    from PyQt5.QtCore import QEvent, Qt
    from PyQt5.QtGui import QMouseEvent
    from PyQt5.QtTest import QTest
    from PyQt5.QtWidgets import QApplication

    clip = d.media.clips[0]
    d.open(clip)
    a = d.wait_for_cell("a.mp4")
    d.wait_until(lambda: a.is_playable, "plays")
    d.run(a, "active", "set_pause", True)
    d.ctx.active_block = a

    for ms in (12_000, 3_000, 7_000):
        _at(d, a, ms, f"at {ms // 1000}s")
        _press(d, Qt.Key_M)

    def times():
        return [b.time_ms for b in a.bookmarks]

    d.check("three added", times() == [3000, 7000, 12000], times())

    _press(d, Qt.Key_M, Qt.ControlModifier)
    d.check("Ctrl+M takes back the last added", times() == [3000, 12000], times())

    shown = a.overlay.bookmark_list
    d.wait_until(lambda: shown.isVisibleTo(a.overlay), "the list up")
    a.overlay.lay_out_now()

    top = shown._rows_top() + shown._row_height()
    cross = shown._delete_rect(top).center()
    QApplication.sendEvent(
        shown,
        QMouseEvent(QEvent.MouseMove, cross, Qt.NoButton, Qt.NoButton, Qt.NoModifier),
    )
    d.pump()
    d.check("the cross under the mouse", shown.is_delete_at(cross.toPoint()))
    d.shot("cross", shown)

    QTest.mouseClick(shown, Qt.LeftButton, Qt.NoModifier, cross.toPoint())
    d.pump()
    d.check("deleted, not asked", times() == [3000], times())
    d.check(
        "no window asking", not d.windows(), [type(w).__name__ for w in d.windows()]
    )
