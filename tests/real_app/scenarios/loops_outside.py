"""A seek outside the loops plays the video from there, so a second loop can
be made beside the first; played to its end, it goes back to the loops."""


def _at(d, a, ms, what):
    d.run(a, "active", "seek", ms)
    d.wait_until(lambda: abs(a.time - ms) < 400, what)


def scenario(d):
    d.open(d.media.clips[0])
    a = d.wait_for_cell("a.mp4")

    # the first loop: 2s to 4s
    _at(d, a, 2_000, "at 2s")
    d.act(a, "Set Loop Start")
    _at(d, a, 4_000, "at 4s")
    d.act(a, "Set Loop End")
    d.check("one loop made", a.video_params.loops == [(2_000, 4_000)])

    # out of it, as a click on the bar would, and played on from there
    _at(d, a, 12_000, "out at 12s")
    d.check("outside the loops", a.video_params.is_outside_loops)
    d.wait_until(lambda: a.time > 13_000, "played on past 13s")

    # the second loop, made out there
    d.act(a, "Set Loop Start")
    _at(d, a, 15_000, "at 15s")
    d.act(a, "Set Loop End")
    loops = a.video_params.loops
    d.check("two loops made", len(loops) == 2, loops)
    d.check("the second playing", not a.video_params.is_outside_loops)
    d.note("two loops", a)

    # out again, near the end of the file: played to it, back to the loops
    length = a.video_driver.length
    _at(d, a, length - 1_500, "out near the end")
    d.wait_until(
        lambda: not a.video_params.is_outside_loops and loops[1][0] <= a.time,
        "back in the loop left once the file ended",
    )
    d.note("back in a loop", a)
