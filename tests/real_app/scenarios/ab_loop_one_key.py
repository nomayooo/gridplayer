"""A-B Loop on one key: start, then end, its title saying which is next."""


def _at(d, a, ms, what):
    d.run(a, "active", "seek", ms)
    d.wait_until(lambda: abs(a.time - ms) < 400, what)


def scenario(d):
    clip = d.media.clips[0]
    d.open(clip)
    a = d.wait_for_cell("a.mp4")
    d.wait_until(lambda: a.is_playable, "plays")
    item = d.ctx.actions["A-B Loop"]

    d.ctx.active_block = a
    d.check("offers the start", item.title == "A-B Loop: Set Start", item.title)
    _at(d, a, 2_000, "at 2s")
    d.act(a, "A-B Loop")
    d.check("begun", a.video_params.loop_start is not None, a.video_params.loop_start)
    d.check("offers the end", item.title == "A-B Loop: Set End", item.title)
    _at(d, a, 4_000, "at 4s")
    d.act(a, "A-B Loop")
    d.check("a loop", len(a.video_params.loops) == 1, a.video_params.loops)
    d.check("offers the start again", item.title == "A-B Loop: Set Start", item.title)
    d.wait_until(lambda: 2_000 - 400 <= a.time <= 4_000 + 400, "in its loop")
    d.shot("looping")
