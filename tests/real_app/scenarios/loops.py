"""Two loops made with the keys' actions play one after the other, round again."""


def _at(d, a, ms, what):
    d.run(a, "active", "seek", ms)
    d.wait_until(lambda: abs(a.time - ms) < 400, what)


def scenario(d):
    clip = d.media.clips[0]
    d.open(clip)
    a = d.wait_for_cell("a.mp4")
    d.note("length", a)

    # the first loop: 2s to 4s
    _at(d, a, 2_000, "at 2s")
    d.act(a, "Set Loop Start")
    _at(d, a, 4_000, "at 4s")
    d.act(a, "Set Loop End")
    first = a.video_params.loops[0]
    d.check("one loop made", len(a.video_params.loops) == 1, a.video_params.loops)

    # the second, later in the file: begun anywhere, moved to 12s, ended at 14s
    d.act(a, "Set Loop Start")
    _at(d, a, 12_000, "at 12s, past the first loop")
    d.act(a, "Set Loop Start")
    _at(d, a, 14_000, "at 14s")
    d.act(a, "Set Loop End")
    d.check("two loops made", len(a.video_params.loops) == 2, a.video_params.loops)
    d.note("two loops", a)

    # Set Loop End with none begun does nothing
    d.act(a, "Set Loop End")
    d.check("end alone does nothing", len(a.video_params.loops) == 2)

    # the second ends, the first plays; it ends, the second plays
    d.wait_until(
        lambda: a.video_params.loop_index == 0 and first[0] <= a.time <= first[1],
        "round to the first loop",
    )
    d.shot("playing the first loop", a)
    d.wait_until(
        lambda: a.video_params.loop_index == 1 and a.time >= 12_000,
        "on to the second loop",
        timeout=10,
    )
    d.wait_until(lambda: a.video_params.loop_index == 0, "round again", timeout=10)

    d.act(a, "Next Loop")
    d.check("next loop", a.video_params.loop_index == 1, a.video_params.loop_index)

    d.act(a, "Remove Last Loop")
    d.check("last taken back", a.video_params.loops == [first], a.video_params.loops)
    d.wait_until(lambda: first[0] <= a.time <= first[1], "the one left plays")

    d.act(a, "Loop Reset")
    d.check("all gone", a.video_params.current_loop is None)
