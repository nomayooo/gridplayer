"""Open Videos, first in the menu while nothing is open: the file dialog in
the folder videos were last opened from, a video picked there opened, and
its folder kept for the next time; not in the menu once something is."""


def _top_of_menu(d):
    from PyQt5.QtWidgets import QApplication

    from gridplayer.player.managers.menu import MenuManager

    # offscreen, the clipboard has nothing at all until something is put on
    # it, which Add - Clipboard asks of it as the menu is made
    QApplication.clipboard().setText("text")

    (manager,) = d.player.findChildren(MenuManager)
    menu = manager.make_menu()
    titles = [action.text() for action in menu.actions()]
    menu.deleteLater()
    return titles


def scenario(d):
    from gridplayer.settings import Settings

    d.ctx.active_block = None
    d.pump()

    titles = _top_of_menu(d)
    d.check("first with nothing open", titles[0] == "Open Videos…", titles[:3])

    clip = d.media.clips[1]
    folder = clip.parent
    # last opened from the one above, the video picked in the one below it
    Settings().set("player/last_open_dir", str(folder.parent))

    def pick(window):
        from pathlib import Path

        d.check(
            "the dialog in the folder last opened from",
            Path(window.directory().absolutePath()) == folder.parent,
            window.directory().absolutePath(),
        )
        # its name typed into the dialog, as a person would: offscreen,
        # its list of the folder is never filled in to pick from
        from PyQt5.QtWidgets import QLineEdit

        name_box = window.findChild(QLineEdit, "fileNameEdit")
        name_box.setText(f"{folder.name}/{clip.name}")
        window.accept()

    d.through_modal(lambda: d.act(None, "Open Videos"), "open videos", pick)

    b = d.wait_for_cell(clip.name)
    d.wait_until(lambda: b.is_playable, "the one picked plays")
    d.check(
        "its folder kept, for the next time",
        Settings().sync_get("player/last_open_dir") == str(folder),
        Settings().sync_get("player/last_open_dir"),
    )

    d.ctx.active_block = None
    titles = _top_of_menu(d)
    d.check("not there once something is", "Open Videos…" not in titles, titles[:3])
