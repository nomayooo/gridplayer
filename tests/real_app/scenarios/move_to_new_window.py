"""Two of three cells picked out with Select (Ctrl+Click) and moved to a new
window: gone from this one, handed over with their loops and places in the
video, and taken in again as the new window takes them.

The new window is another process, which a scenario cannot drive: its start
is caught here, and the cells handed to it opened in this player instead,
as the new one opens them.
"""


def _at(d, a, ms, what):
    d.run(a, "active", "seek", ms)
    d.wait_until(lambda: abs(a.time - ms) < 400, what)


def scenario(d):
    from pathlib import Path

    from gridplayer.models.moved_cells import MovedCells
    from gridplayer.player.managers import new_window

    a_clip, b_clip, c_clip = d.media.clips[:3]
    d.open(a_clip, b_clip, c_clip)
    a = d.wait_for_cell("a.mp4")
    b = d.wait_for_cell("b.mp4")
    c = d.wait_for_cell("c.mp4")

    # b with a loop, 3s to 6s, to go along with it
    _at(d, b, 3_000, "b at 3s")
    d.act(b, "Set Loop Start")
    _at(d, b, 6_000, "b at 6s")
    d.act(b, "Set Loop End")
    loops = list(b.video_params.loops)

    d.act(a, "Select")
    d.act(b, "Select")
    d.check("a and b picked out", a.is_selected and b.is_selected and not c.is_selected)
    d.check(
        "marked so",
        a.overlay.selection_mark.isVisibleTo(a.overlay)
        and not c.overlay.selection_mark.isVisibleTo(c.overlay),
    )
    d.shot("two picked out")

    d.act(a, "Select")
    d.check("picked again, let go", not a.is_selected)
    d.act(a, "Select")

    started = []

    def start_detached(program, args):
        started.append((program, args))
        return True, 1

    new_window.QProcess.startDetached = start_detached

    d.act(c, "Move to New Window")

    d.check("a new window started", len(started) == 1, started)
    _, args = started[0]
    moved_file = Path(args[args.index("--moved-cells") + 1])

    d.wait_until(lambda: len(d.cells) == 1, "the two gone from here")
    d.check("c left", d.cells[0] is c)

    moved = MovedCells.model_validate_json(moved_file.read_bytes())
    uris = [str(m.cell.video.uri) for m in moved.cells]
    d.check("a and b handed over", uris == [str(a_clip), str(b_clip)], uris)
    d.check("b's loop with it", moved.cells[1].cell.video.loops == loops)

    # as the new window takes them in
    d.player.open_moved_cells(moved_file)
    d.wait_until(lambda: len(d.cells) == 3, "taken in")
    b2 = d.cell("b.mp4")
    d.wait_until(lambda: b2.is_playable, "b plays again")
    d.check("its loop", b2.video_params.loops == loops, b2.video_params.loops)
    d.wait_until(lambda: 3_000 - 400 <= b2.time <= 6_000 + 400, "in its loop")
    d.check("the file let go", not moved_file.exists())
    d.check("closed without asking", d.ctx.commands.check_playlist_save() is True)
    d.shot("taken in")
