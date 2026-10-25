"""A folder of favourites opened from Manage Favourites with Open, and a
video with a double click: into the grid, each where it was kept, the
window staying open for more."""


def scenario(d):
    from gridplayer.models.favourites import (
        FavouriteFolder,
        Favourites,
        FavouriteVideo,
    )
    from gridplayer.settings import Settings

    a_clip, b_clip, c_clip = d.media.clips[:3]
    Settings().set(
        "favourites",
        Favourites(
            [
                FavouriteVideo(name="Third", path=c_clip),
                FavouriteFolder(
                    name="Pair",
                    items=[
                        FavouriteVideo(name="First", path=a_clip, position=4_000),
                        FavouriteVideo(name="Second", path=b_clip),
                    ],
                ),
            ]
        ),
    )

    d.open(a_clip)
    a = d.wait_for_cell("a.mp4")
    d.wait_until(lambda: a.is_playable, "a plays")

    def open_from_it(window):
        folder = window.tree.topLevelItem(1)
        folder.setSelected(True)
        d.check("open offered", window.open_button.isEnabled())
        window.open_button.click()
        d.wait_until(lambda: len(d.cells) == 3, "the folder's two opened")
        d.check("the window still open", window.isVisible())

        window.tree.clearSelection()
        window.tree.itemDoubleClicked.emit(window.tree.topLevelItem(0), 0)
        d.wait_until(lambda: len(d.cells) == 4, "the double clicked one opened")
        d.shot("opened from the manager", window)
        window.reject()

    d.through_modal(lambda: d.act(a, "Manage Favourites"), "manage", open_from_it)

    uris = [str(c.video_params.uri) for c in d.cells]
    d.check(
        "the folder's in order, then the one double clicked",
        uris[1:] == [str(a_clip), str(b_clip), str(c_clip)],
        uris,
    )
    first = d.cells[1]
    d.wait_until(lambda: first.is_playable, "the first of them plays")
    d.wait_until(lambda: first.time > 3_500, "from where it was kept", timeout=10)
    d.check("not from the start", first.time > 3_500, first.time)
