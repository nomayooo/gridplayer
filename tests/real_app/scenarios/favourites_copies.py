"""One file open four times, at different places in it, made favourites all
at once: kept apart as "a.mp4", "a.mp4 (2)" and on, each opening where
its copy was; added again from other places, the four replaced, not more.
"""


def _at(d, cell, ms, what):
    d.run(cell, "active", "seek", ms)
    d.wait_until(lambda: abs(cell.time - ms) < 400, what)


def _add_all(d, name):
    def accept(window):
        window.accept()

    d.through_modal(lambda: d.act(d.cells[0], "Add All to Favourites"), name, accept)


def scenario(d):
    from gridplayer.models.favourites import Favourites
    from gridplayer.settings import Settings

    Settings().set("favourites", Favourites())

    clip = d.media.clips[0]
    d.open(clip, clip, clip, clip)
    d.wait_until(lambda: len(d.cells) == 4, "four copies")
    for cell in d.cells:
        d.wait_until(lambda cell=cell: cell.is_playable, "a copy plays")

    for cell, ms in zip(d.cells, (2_000, 6_000, 10_000, 14_000)):
        _at(d, cell, ms, f"a copy at {ms}")
        d.run(cell, "active", "set_pause", True)

    _add_all(d, "add four")

    title = d.cells[0].title
    numbered = [title, f"{title} (2)", f"{title} (3)", f"{title} (4)"]

    kept = Settings().get("favourites").root
    names = [v.name for v in kept]
    d.check("four kept", names == numbered, names)
    at = [v.position for v in kept]
    d.check(
        "each where its copy was",
        all(abs(p - ms) < 1_000 for p, ms in zip(at, (2_000, 6_000, 10_000, 14_000))),
        at,
    )

    for cell, ms in zip(d.cells, (3_000, 7_000, 11_000, 15_000)):
        _at(d, cell, ms, f"a copy moved to {ms}")

    _add_all(d, "add four again")

    kept = Settings().get("favourites").root
    names = [v.name for v in kept]
    d.check("still four", names == numbered, names)
    at = [v.position for v in kept]
    d.check(
        "each where its copy is now",
        all(abs(p - ms) < 1_000 for p, ms in zip(at, (3_000, 7_000, 11_000, 15_000))),
        at,
    )
