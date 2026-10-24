"""A selected cell keeps its mark once its controls fade out on their
timeout, its controls back with the mouse; let go, its overlay fades
with them as any other cell's does."""

SETTINGS = {"playlist/overlay_hide_on_timeout": True}


def scenario(d):
    import time

    clips = d.media.clips[:2]
    d.open(*clips)
    a = d.wait_for_cell("a.mp4")
    b = d.wait_for_cell("b.mp4")
    d.wait_until(lambda: a.is_playable and b.is_playable, "both play")
    d.act(a, "Select")
    a.show_overlay()
    d.check("marked", a.overlay.isVisible() and a.overlay.selection_mark.isVisible())
    end = time.time() + d.ctx.overlay_timeout + 1.5
    d.wait_until(lambda: time.time() >= end, "controls timed out", timeout=30)
    d.check(
        "still marked",
        a.overlay.isVisible() and a.overlay.selection_mark.isVisible(),
        {
            "overlay": a.overlay.isVisible(),
            "mark": a.overlay.selection_mark.isVisible(),
            "controls": a.overlay.control_widget.isVisible(),
        },
    )
    d.check("b's overlay gone", not b.overlay.isVisible())
    d.shot("faded")
    a.show_overlay()
    d.check("controls back", a.overlay.control_widget.isVisible())
    d.act(a, "Select")
    end = time.time() + d.ctx.overlay_timeout + 1.5
    d.wait_until(lambda: time.time() >= end, "timed out again", timeout=30)
    d.check("unmarked, gone", not a.overlay.isVisible(), a.overlay.isVisible())
