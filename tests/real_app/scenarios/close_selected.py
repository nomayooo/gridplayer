"""Close with cells picked out: asked from one of them, all of them closed
at once; asked from one not picked, that one alone, the others still
picked."""


def scenario(d):
    clips = d.media.clips[:3]
    d.open(*clips)
    a = d.wait_for_cell("a.mp4")
    b = d.wait_for_cell("b.mp4")
    c = d.wait_for_cell("c.mp4")

    d.act(a, "Select")
    d.act(b, "Select")
    d.check("two picked out", a.is_selected and b.is_selected and not c.is_selected)

    # from the menu of the one not picked: that one alone
    d.act(c, "Close")
    d.wait_until(lambda: len(d.cells) == 2, "the one not picked closed")
    d.check("the picked ones kept", a.is_selected and b.is_selected)

    # from one picked: both
    d.act(a, "Close")
    d.wait_until(lambda: not d.cells, "the two picked out closed at once")
