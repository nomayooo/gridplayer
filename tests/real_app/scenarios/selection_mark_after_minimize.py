"""The selection mark once the window is minimized and back: Qt hides each
cell as the window is minimized and shows it again as it comes back, which
the offscreen platform, minimizing nothing, does not; sent to them here."""


def _state(a):
    return {
        "overlay": a.overlay.isVisible(),
        "mark": a.overlay.selection_mark.isVisible(),
        "controls": a.overlay.control_widget.isVisible(),
    }


def scenario(d):
    from PyQt5.QtGui import QHideEvent, QShowEvent
    from PyQt5.QtWidgets import QApplication

    clips = d.media.clips[:2]
    d.open(*clips)
    a = d.wait_for_cell("a.mp4")
    b = d.wait_for_cell("b.mp4")
    d.wait_until(lambda: a.is_playable and b.is_playable, "both play")
    d.act(a, "Select")
    d.check("marked", a.overlay.selection_mark.isVisible(), _state(a))

    for cell in (a, b):
        QApplication.sendEvent(cell, QHideEvent())
    d.pump()
    d.check("hidden as minimized", not a.overlay.isVisible(), _state(a))

    for cell in (a, b):
        QApplication.sendEvent(cell, QShowEvent())
    d.pump(0.3)
    d.check("marked again", a.overlay.selection_mark.isVisible(), _state(a))
    d.check("its controls not", not a.overlay.control_widget.isVisible(), _state(a))
    d.check("b's overlay not back", not b.overlay.isVisible(), _state(b))
    d.shot("back")
