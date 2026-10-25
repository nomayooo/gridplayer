"""Next / Previous Loop (Ctrl+. / Ctrl+,) with a loop begun and not
finished: from one start marker on the bar to the next, the begun one's
too, round the ends of them; with one loop alone, back to its start."""


def _at(d, a, ms, what):
    d.run(a, "active", "seek", ms)
    d.wait_until(lambda: abs(a.time - ms) < 400, what)


def _press(d, key):
    from PyQt5.QtCore import Qt
    from PyQt5.QtTest import QTest
    from PyQt5.QtWidgets import QApplication

    target = QApplication.focusWidget() or d.player
    QTest.keyClick(target, key, Qt.ControlModifier)
    d.pump(0.3)


def scenario(d):
    from PyQt5.QtCore import Qt

    clip = d.media.clips[0]
    d.open(clip)
    a = d.wait_for_cell("a.mp4")
    d.wait_until(lambda: a.is_playable, "plays")
    d.run(a, "active", "set_pause", True)
    d.player.activateWindow()
    d.ctx.active_block = a

    # one loop alone, 2-4s: Next back to its start
    _at(d, a, 2_000, "at 2s")
    d.act(a, "A-B Loop")
    _at(d, a, 4_000, "at 4s")
    d.act(a, "A-B Loop")
    _at(d, a, 3_500, "at 3.5s")
    _press(d, Qt.Key_Period)
    d.wait_until(lambda: abs(a.time - 2_000) < 400, "one loop: back to its start")

    # another, 12-14s, and one begun at 8s
    _at(d, a, 12_000, "at 12s")
    d.act(a, "A-B Loop")
    _at(d, a, 14_000, "at 14s")
    d.act(a, "A-B Loop")
    _at(d, a, 8_000, "at 8s")
    d.act(a, "A-B Loop")
    d.check("one begun", a.video_params.loop_start is not None)

    # the start markers: 2s, 8s (begun), 12s
    for ms, what in (
        (12_000, "next: 12s"),
        (2_000, "next round: 2s"),
        (8_000, "next: 8s"),
    ):
        _press(d, Qt.Key_Period)
        d.wait_until(lambda ms=ms: abs(a.time - ms) < 400, what)

    for ms, what in ((2_000, "previous: 2s"), (12_000, "previous round: 12s")):
        _press(d, Qt.Key_Comma)
        d.wait_until(lambda ms=ms: abs(a.time - ms) < 400, what)

    d.check("still begun", a.video_params.loop_start is not None)
    d.check("the loops kept", len(a.video_params.loops) == 2, a.video_params.loops)
