"""A-B loop markers taken back one at a time with Undo Loop Marker (Ctrl+Z):
the end of a loop made, which is left begun from its start and given
another end; then the start itself."""


def _at(d, a, ms, what):
    d.run(a, "active", "seek", ms)
    d.wait_until(lambda: abs(a.time - ms) < 400, what)


def _press_undo(d):
    from PyQt5.QtCore import Qt
    from PyQt5.QtTest import QTest
    from PyQt5.QtWidgets import QApplication

    target = QApplication.focusWidget() or d.player
    QTest.keyClick(target, Qt.Key_Z, Qt.ControlModifier)
    d.pump(0.3)


def scenario(d):
    clip = d.media.clips[0]
    d.open(clip)
    a = d.wait_for_cell("a.mp4")
    d.wait_until(lambda: a.is_playable, "plays")
    d.player.activateWindow()
    d.ctx.active_block = a

    _at(d, a, 2_000, "at 2s")
    d.act(a, "A-B Loop")
    _at(d, a, 4_000, "at 4s")
    d.act(a, "A-B Loop")
    d.check("a loop", a.video_params.loops == [(2_000, 4_000)], a.video_params.loops)

    _press_undo(d)
    params = a.video_params
    d.check("its end taken back", params.loops == [], params.loops)
    d.check("begun from its start", params.loop_start == 2_000, params.loop_start)
    item = d.ctx.actions["A-B Loop"]
    d.check("the end offered again", item.title == "A-B Loop: Set End", item.title)

    _at(d, a, 6_000, "at 6s")
    d.act(a, "A-B Loop")
    d.check("another end", a.video_params.loops == [(2_000, 6_000)])
    d.wait_until(lambda: 2_000 - 400 <= a.time <= 6_000 + 400, "in it")

    _press_undo(d)
    _press_undo(d)
    d.check("nothing left", a.video_params.loops == [], a.video_params.loops)
    d.check("not begun", a.video_params.loop_start is None)
