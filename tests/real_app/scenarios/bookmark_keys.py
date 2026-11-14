"""Bookmarks on their own keys, as the viewer presses them: M marks where the
video is, Alt+. and Alt+, go to the next and the one before, round again;
and Bookmarks in the video's menu itself, not in Playback."""


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
    from PyQt5.QtCore import Qt
    from PyQt5.QtWidgets import QApplication

    from gridplayer.player.managers.menu import MenuManager

    clip = d.media.clips[0]
    d.open(clip)
    a = d.wait_for_cell("a.mp4")
    d.wait_until(lambda: a.is_playable, "plays")
    d.run(a, "active", "set_pause", True)
    d.ctx.active_block = a

    for ms in (3_000, 9_000, 15_000):
        _at(d, a, ms, f"at {ms // 1000}s")
        _press(d, Qt.Key_M)

    times = [b.time_ms for b in a.bookmarks]
    d.check("three marked with M", len(times) == 3, times)

    _at(d, a, 5_000, "at 5s")
    _press(d, Qt.Key_Period, Qt.AltModifier)
    d.wait_until(lambda: abs(a.time - times[1]) < 400, "Alt+. to the next")

    _press(d, Qt.Key_Period, Qt.AltModifier)
    d.wait_until(lambda: abs(a.time - times[2]) < 400, "and the next")

    _press(d, Qt.Key_Period, Qt.AltModifier)
    d.wait_until(lambda: abs(a.time - times[0]) < 400, "round to the first")

    _press(d, Qt.Key_Comma, Qt.AltModifier)
    d.wait_until(lambda: abs(a.time - times[2]) < 400, "Alt+, round to the last")

    # offscreen, the clipboard has nothing at all until something is put on
    # it, which Add - Clipboard asks of it as the menu is made
    QApplication.clipboard().setText("text")

    (manager,) = d.player.findChildren(MenuManager)
    menu = manager.make_menu()
    top = [action.text() for action in menu.actions()]
    d.check("Bookmarks at the top of the menu", "Bookmarks" in top, top)
    playback = next(x for x in menu.actions() if x.text() == "Playback").menu()
    inside = [action.text() for action in playback.actions()]
    d.check("not in Playback", "Bookmarks" not in inside, inside)
    menu.deleteLater()
