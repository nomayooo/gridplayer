"""A video with a loop made a favourite, kept, and opened again from the
Favourites menu into a cell of its own beside it, its loop with it."""


def _at(d, a, ms, what):
    d.run(a, "active", "seek", ms)
    d.wait_until(lambda: abs(a.time - ms) < 400, what)


def scenario(d):
    from gridplayer.settings import Settings

    clip = d.media.clips[0]
    d.open(clip)
    a = d.wait_for_cell("a.mp4")

    # a loop, 2s to 4s, to be kept with it
    _at(d, a, 2_000, "at 2s")
    d.act(a, "Set Loop Start")
    _at(d, a, 4_000, "at 4s")
    d.act(a, "Set Loop End")
    loops = list(a.video_params.loops)
    d.check("one loop made", len(loops) == 1, loops)

    def name_it(window):
        d.check("offered with its loop", not window.loops_note.isHidden())
        window.name.setText("My clip")
        window.accept()

    d.through_modal(lambda: d.act(a, "Add to Favourites"), "add to favourites", name_it)

    kept = Settings().get("favourites")
    d.check(
        "kept with the settings",
        [(f.name, f.path, f.loops) for f in kept.root] == [("My clip", clip, loops)],
        kept.model_dump(mode="json"),
    )

    d.check("in the menu", d.menu(a, "menu_generator_favourites") == ["My clip"])

    # opened again: into a cell of its own, the first one left playing
    d.choose(a, "menu_generator_favourites", "My clip")
    d.wait_until(lambda: len(d.cells) == 2, "a second cell")
    b = d.cells[1]
    d.wait_until(lambda: b.is_playable, "the favourite plays")
    d.check("the same file", b.video_params.uri == clip, str(b.video_params.uri))
    d.check("with its loop", b.video_params.loops == loops, b.video_params.loops)
    d.check("the first still there", d.cells[0] is a)
    d.wait_until(lambda: 2_000 - 400 <= b.time <= 4_000 + 400, "playing in its loop")
    d.shot("opened from favourites")

    def look(window):
        d.check("in the manager", window.tree.topLevelItem(0).text(0) == "My clip")

    d.through_modal(lambda: d.act(a, "Manage Favourites"), "manage favourites", look)
