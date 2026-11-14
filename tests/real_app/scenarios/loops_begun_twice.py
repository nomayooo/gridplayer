"""A-B Loop pressed for a start, then again before it for another start:
both kept and marked on the bar; the next press past the last one finishes
that one, the first then begun again, and the press after finishes it."""


def _at(d, a, ms, what):
    d.run(a, "active", "seek", ms)
    d.wait_until(lambda: abs(a.time - ms) < 400, what)


def scenario(d):
    clip = d.media.clips[0]
    d.open(clip)
    a = d.wait_for_cell("a.mp4")
    d.wait_until(lambda: a.is_playable, "plays")
    d.run(a, "active", "set_pause", True)
    params = a.video_params

    _at(d, a, 8_000, "at 8s")
    d.act(a, "A-B Loop")
    d.check("a loop begun at 8s", params.loop_start is not None, params.loop_start)
    first = params.loop_start

    # back before it, a second start: the first kept
    _at(d, a, 2_000, "at 2s")
    d.act(a, "A-B Loop")
    second = params.loop_start
    d.check(
        "two begun", params.earlier_loop_starts == [first], params.earlier_loop_starts
    )
    d.check(
        "both on the bar",
        len(a.overlay.progress_bar.other_loops) == 1,
        a.overlay.progress_bar.other_loops,
    )
    d.shot("two starts", a)

    # past the second: it is the one finished, the first begun again
    _at(d, a, 5_000, "at 5s")
    d.act(a, "A-B Loop")
    d.check("the last begun finished", len(params.loops) == 1, params.loops)
    d.check(
        "from the second start",
        params.loops[0][0] == second,
        params.loops,
    )
    d.check("the first begun again", params.loop_start == first, params.loop_start)

    # and past the first: it is finished too
    _at(d, a, 12_000, "at 12s")
    d.act(a, "A-B Loop")
    d.check("both finished", len(params.loops) == 2, params.loops)
    d.check("none begun", params.loop_start is None and not params.earlier_loop_starts)
    d.check("from the first start", params.loops[1][0] == first, params.loops)
    d.shot("two loops", a)
