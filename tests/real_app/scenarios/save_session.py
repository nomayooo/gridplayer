"""The session saved to favourites: this window's videos as they are, and
another window's, asked of it over its socket, each in a numbered folder of
a folder named by the date and time; opened again into an empty window,
the first here and the other in a new window.

The other window is a server of its own in this process, as another
GridPlayer's would be; its new window's start is caught.
"""


def _at(d, a, ms, what):
    d.run(a, "active", "seek", ms)
    d.wait_until(lambda: abs(a.time - ms) < 400, what)


def scenario(d):
    import re
    from pathlib import Path

    from gridplayer.models.favourites import Favourites, FavouriteVideo
    from gridplayer.models.moved_cells import MovedCells
    from gridplayer.player.managers import new_window
    from gridplayer.settings import Settings
    from gridplayer.utils.app_dir import get_app_data_dir
    from gridplayer.utils.session_server import SessionServer

    Settings().set("favourites", Favourites())

    a_clip, b_clip, c_clip = d.media.clips[:3]

    other = SessionServer(
        provider=lambda: [
            FavouriteVideo(name="c.mp4", path=c_clip, position=7_000).model_dump(
                mode="json"
            )
        ],
        registry_dir=get_app_data_dir() / "windows",
    )
    d.check("the other window serves", other.start())

    d.open(a_clip, b_clip)
    a = d.wait_for_cell("a.mp4")
    b = d.wait_for_cell("b.mp4")
    d.wait_until(lambda: a.is_playable and b.is_playable, "both play")
    _at(d, a, 4_000, "a at 4s")
    d.run(a, "active", "set_pause", True)

    def saved(box):
        d.check("said where", "Saved to your favourites as" in box.text(), box.text())
        box.accept()

    d.through_modal(lambda: d.act(a, "Save Session to Favourites"), "saved", saved)

    root = Settings().get("favourites").root
    d.check("one session folder", len(root) == 1, root)
    session = root[0]
    d.check(
        "named by the date and time",
        re.fullmatch(r"\d{4}-\d\d-\d\d \d\d:\d\d:\d\d", session.name) is not None,
        session.name,
    )
    d.check("a folder a window", [f.name for f in session.items] == ["1", "2"])
    mine, theirs = session.items
    d.check(
        "this window's first, in its order",
        [v.name for v in mine.items] == ["a.mp4", "b.mp4"],
        [v.name for v in mine.items],
    )
    d.check(
        "where a was", abs(mine.items[0].position - 4_000) < 500, mine.items[0].position
    )
    d.check(
        "the other's second",
        [(v.name, v.position) for v in theirs.items] == [("c.mp4", 7_000)],
    )
    other.stop()

    # opened again into an empty window: the first here, the second apart
    started = []

    def start_detached(program, args):
        started.append(Path(args[args.index("--moved-cells") + 1]))
        return True

    new_window.QProcess.startDetached = start_detached

    for cell in list(d.cells):
        cell.close()
    d.wait_until(lambda: len(d.cells) == 0, "the grid emptied")

    d.run(None, "open_favourites_folder", (0,))
    d.wait_until(lambda: len(d.cells) == 2, "this window's back here")
    first = d.cells[0]
    d.wait_until(lambda: first.is_playable, "it plays")
    d.wait_until(lambda: first.time > 3_500, "a from where it was", timeout=10)
    d.check("the other's in a new window", len(started) == 1, started)
    moved = MovedCells.model_validate_json(started[0].read_bytes())
    d.check(
        "with c at 7s",
        [m.cell.video.current_position for m in moved.cells] == [7_000],
    )
    started[0].unlink(missing_ok=True)
