"""A video with a loop made a favourite, kept, and opened again from the
Favourites menu into a cell of its own beside it, its loop with it; then
again with a loop begun and not finished, which it is opened with too, saved
over the favourite the file was already."""


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

    # a loop begun at 8s and not finished: kept, and begun again on opening
    _at(d, a, 8_000, "at 8s")
    d.act(a, "Set Loop Start")
    loop_start = a.video_params.loop_start
    d.check("a loop begun", loop_start is not None, loop_start)

    # the same file again: offered as the favourite it is, which it replaces
    # under the same name; under another it would be one more
    def name_begun(window):
        d.check("offered with the loop begun", not window.loop_start_note.isHidden())
        d.check("as the one kept", not window.kept_note.isHidden())
        d.check("under its name", window.name.text() == "My clip", window.name.text())
        window.name.setText("Begun")
        d.check("renamed, one more", window.kept_note.isHidden())
        window.name.setText("My clip")
        window.accept()

    d.through_modal(lambda: d.act(a, "Add to Favourites"), "add begun", name_begun)

    kept = Settings().get("favourites").root
    d.check("replaced, not added", len(kept) == 1, [f.name for f in kept])
    begun = kept[-1]
    d.check(
        "the loop begun kept",
        (begun.loops, begun.loop_start) == (loops, loop_start),
        begun.model_dump(mode="json"),
    )

    d.choose(a, "menu_generator_favourites", "My clip")
    d.wait_until(lambda: len(d.cells) == 3, "a third cell")
    c = d.cells[2]
    d.wait_until(lambda: c.is_playable, "the begun favourite plays")
    d.check("with the loop begun", c.video_params.loop_start == loop_start)
    d.check("and the loop made", c.video_params.loops == loops, c.video_params.loops)
    # on from there, not from the start of the file: what time it says
    # before it plays is only where it was asked to be
    d.wait_until(lambda: c.time > loop_start + 300, "playing on", timeout=5)
    d.check("from the loop start", c.time < loop_start + 2_500, c.time)
    d.shot("opened with a loop begun")
