"""A favourite shown moving in Manage Favourites: the mouse rested on its
row, a box by it shows its frames as they come, a few places of it; gone
as the mouse leaves."""


def scenario(d):
    from PyQt5.QtCore import QEvent

    from gridplayer.dialogs.favourites import ManageFavouritesDialog
    from gridplayer.models.favourites import Favourites, FavouriteVideo
    from gridplayer.settings import Settings

    clip = d.media.clips[0]
    Settings().set("favourites", Favourites([FavouriteVideo(name="Clip", path=clip)]))

    d.open(clip)
    a = d.wait_for_cell("a.mp4")

    def look(window):
        d.check("the Manage window", isinstance(window, ManageFavouritesDialog))
        row = window.tree.topLevelItem(0)

        window._hovered(row)
        d.wait_until(lambda: window._preview.isVisible(), "shown moving by its row")

        frames = []
        window._previewer.frame.connect(lambda image: frames.append(image))
        d.wait_until(lambda: len(frames) >= 20, "its frames coming")
        d.check(
            "small, as it is shaped",
            frames[-1].width() <= 320 and frames[-1].height() <= 320,
            (frames[-1].width(), frames[-1].height()),
        )
        d.shot("hovered", window._preview)

        window.eventFilter(window.tree.viewport(), QEvent(QEvent.Leave))
        d.check("gone as the mouse leaves", not window._preview.isVisible())

    d.through_modal(lambda: d.act(a, "Manage Favourites"), "manage", look)
