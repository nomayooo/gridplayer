"""Jump and loop keys rebound on the Shortcuts page work at once; the old ones
no longer do."""


def _keys(d, action_id):
    return [key.toString() for key in d.player._context.actions[action_id].shortcuts()]


def _press(d, key, modifiers=None):
    from PyQt5.QtCore import Qt
    from PyQt5.QtTest import QTest
    from PyQt5.QtWidgets import QApplication

    target = QApplication.focusWidget() or d.player
    QTest.keyClick(target, key, modifiers or Qt.NoModifier)


def scenario(d):
    from PyQt5.QtCore import Qt

    d.open(d.media.clips[0])
    a = d.wait_for_cell("a.mp4")
    d.check("Set Loop Start is on , by default", _keys(d, "Set Loop Start") == [","])
    d.check("50% is on 5 by default", _keys(d, "50%") == ["5"])

    def rebind(dialog):
        dialog.show_page("shortcuts")
        editor = dialog.widget("player/keymap")
        editor.tree.set_action_shortcuts("Set Loop Start", ["Q"])
        editor.tree.set_action_shortcuts("50%", ["Ctrl+5"])
        dialog.accept()

    d.through_modal(lambda: d.act(a, "Settings"), "rebind", rebind)
    d.check("Set Loop Start is on Q", _keys(d, "Set Loop Start") == ["Q"])
    d.check("50% is on Ctrl+5", _keys(d, "50%") == ["Ctrl+5"])

    d.player.activateWindow()
    d.pump(0.3)
    length = a.video_driver.length

    _press(d, Qt.Key_5, Qt.ControlModifier)
    d.wait_until(lambda: abs(a.time - length / 2) < 1_500, "at 50% by Ctrl+5")

    _press(d, Qt.Key_Q)
    d.wait_until(lambda: a.video_params.loop_start is not None, "loop begun by Q")
    begun = a.video_params.loop_start

    d.run(a, "active", "seek", 2_000)
    d.wait_until(lambda: abs(a.time - 2_000) < 400, "at 2s")
    _press(d, Qt.Key_Comma)
    _press(d, Qt.Key_5)
    d.pump(0.5)
    loop_start = a.video_params.loop_start
    d.check(", no longer begins a loop", loop_start == begun, loop_start)
    d.check("5 no longer jumps to 50%", a.time < length / 4, a.time)
