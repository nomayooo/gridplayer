"""The loops made on a file come back with it: opened again after its cell
was closed, and gone back to from the next file in its folder."""


def _at(d, a, ms, what):
    d.run(a, "active", "seek", ms)
    d.wait_until(lambda: abs(a.time - ms) < 400, what)


def _make_loop(d, a, start_ms, end_ms):
    _at(d, a, start_ms, f"at {start_ms}ms")
    d.act(a, "Set Loop Start")
    _at(d, a, end_ms, f"at {end_ms}ms")
    d.act(a, "Set Loop End")


def scenario(d):
    clip = d.media.clips[0]
    d.open(clip)
    a = d.wait_for_cell("a.mp4")

    _make_loop(d, a, 2_000, 4_000)
    _make_loop(d, a, 12_000, 14_000)
    made = list(a.video_params.loops)
    d.check("two loops made", len(made) == 2, made)

    # closed, and opened again in a cell of its own
    d.act(a, "Close")
    d.wait_until(lambda: not d.cells, "the cell is gone")

    d.open(clip)
    a = d.wait_for_cell("a.mp4")
    d.check(
        "opened again with its loops",
        a.video_params.loops == made,
        a.video_params.loops,
    )
    d.wait_until(
        lambda: made[0][0] - 400 <= a.time <= made[0][1] + 400,
        "playing the first of them",
    )
    d.shot("opened again, looping", a)

    # on to the next file in the folder: none of its own; and back
    d.act(a, "Play Next File")
    b = d.wait_for_cell("b.mp4")
    d.check("the next file has none", b.video_params.loops == [], b.video_params.loops)

    d.act(b, "Play Previous File")
    a = d.wait_for_cell("a.mp4")
    d.check("back with its loops", a.video_params.loops == made, a.video_params.loops)

    # reset by the viewer: forgotten for the file
    d.act(a, "Loop Reset")
    d.act(a, "Close")
    d.wait_until(lambda: not d.cells, "the cell is gone again")

    d.open(clip)
    a = d.wait_for_cell("a.mp4")
    d.check("reset, opened without", a.video_params.loops == [], a.video_params.loops)
