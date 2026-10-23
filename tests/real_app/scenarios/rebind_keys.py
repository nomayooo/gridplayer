"""Jump and loop keys rebound on the Shortcuts page work at once; the old ones
no longer do. The new keys are free ones, so no other action loses its own."""


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

    from gridplayer.settings import Settings

    d.open(d.media.clips[0])
    a = d.wait_for_cell("a.mp4")
    d.check("Set Loop Start is on , by default", _keys(d, "Set Loop Start") == [","])
    d.check("50% is on 5 by default", _keys(d, "50%") == ["5"])

    def rebind(dialog):
        dialog.show_page("shortcuts")
        editor = dialog.widget("player/keymap")
        editor.tree.set_action_shortcuts("Set Loop Start", ["Alt+L"])
        editor.tree.set_action_shortcuts("50%", ["F8"])
        dialog.accept()

    d.through_modal(lambda: d.act(a, "Settings"), "rebind", rebind)
    d.check("Set Loop Start is on Alt+L", _keys(d, "Set Loop Start") == ["Alt+L"])
    d.check("50% is on F8", _keys(d, "50%") == ["F8"])
    saved = dict(Settings().get("player/keymap").root)
    d.check(
        "only the two are saved",
        saved == {"Set Loop Start": ["Alt+L"], "50%": ["F8"]},
        saved,
    )

    d.player.activateWindow()
    d.pump(0.3)
    length = a.video_driver.length

    _press(d, Qt.Key_F8)
    d.wait_until(lambda: abs(a.time - length / 2) < 1_500, "at 50% by F8")

    _press(d, Qt.Key_L, Qt.AltModifier)
    d.wait_until(lambda: a.video_params.loop_start is not None, "loop begun by Alt+L")
    begun = a.video_params.loop_start

    d.run(a, "active", "seek", 2_000)
    d.wait_until(lambda: abs(a.time - 2_000) < 400, "at 2s")
    _press(d, Qt.Key_Comma)
    _press(d, Qt.Key_5)
    d.pump(0.5)
    loop_start = a.video_params.loop_start
    d.check(", no longer begins a loop", loop_start == begun, loop_start)
    d.check("5 no longer jumps to 50%", a.time < length / 4, a.time)
