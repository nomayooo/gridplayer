"""All three videos open made favourites at once, into a folder made for
them, each under its own name and with its loop; and opened again from that
folder all at once."""


def _at(d, a, ms, what):
    d.run(a, "active", "seek", ms)
    d.wait_until(lambda: abs(a.time - ms) < 400, what)


def scenario(d):
    from gridplayer.models.favourites import FavouriteFolder, Favourites
    from gridplayer.settings import Settings

    clips = d.media.clips[:3]
    d.open(*clips)
    a = d.wait_for_cell("a.mp4")
    b = d.wait_for_cell("b.mp4")
    d.wait_for_cell("c.mp4")

    # b with a loop, 2s to 4s
    _at(d, b, 2_000, "b at 2s")
    d.act(b, "Set Loop Start")
    _at(d, b, 4_000, "b at 4s")
    d.act(b, "Set Loop End")
    loops = list(b.video_params.loops)

    # a folder to put them in, there already
    Settings().set("favourites", Favourites([FavouriteFolder(name="This grid")]))

    def put_them(window):
        d.check("three to add", "3" in window.count_note.text())
        d.check("none left out", window.left_out_note.isHidden())
        window.folder.setCurrentIndex(1)
        d.check("in the folder", window.selected_folder == (0,))
        window.accept()

    d.through_modal(lambda: d.act(a, "Add All to Favourites"), "add all", put_them)

    folder = Settings().get("favourites").items_at((0,))
    d.check(
        "each a favourite, in the grid's order",
        [f.path for f in folder] == list(clips),
        [str(f.path) for f in folder],
    )
    d.check(
        "under their names", [f.name for f in folder] == ["a.mp4", "b.mp4", "c.mp4"]
    )
    d.check("b's loop with it", folder[1].loops == loops, folder[1].loops)

    # Open All of the folder
    d.run(a, "open_favourites_folder", (0,))
    d.wait_until(lambda: len(d.cells) == 6, "the three opened again")
    d.shot("opened again")
