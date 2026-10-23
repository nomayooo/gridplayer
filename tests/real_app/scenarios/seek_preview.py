"""Hovering the seek bar shows a picture of the video at the time under the
mouse, above it in the hover label; another time, another picture; none with
the setting off."""


def _hover(bar, fraction):
    from PyQt5.QtCore import QEvent, QPoint, Qt
    from PyQt5.QtGui import QMouseEvent
    from PyQt5.QtWidgets import QApplication

    pos = QPoint(round(bar.width() * fraction), bar.height() // 2)
    move = QMouseEvent(QEvent.MouseMove, pos, Qt.NoButton, Qt.NoButton, Qt.NoModifier)
    QApplication.sendEvent(bar, move)


def scenario(d):
    from gridplayer.settings import Settings

    d.open(d.media.clips[0])
    a = d.wait_for_cell("a.mp4")
    d.player.resize(900, 520)
    d.act(a, "Play / Pause")
    d.pump(0.3)

    bar = a.overlay.progress_bar
    label = a.overlay.floating_progress

    _hover(bar, 0.25)
    d.wait_until(lambda: label.preview is not None, "a picture at 25%")
    d.check("the label is shown", label.isVisible())
    d.check(
        "the picture is above the time, in the label",
        label.height() > label.preview.height() // 2,
        (label.width(), label.height()),
    )
    first = label.preview
    d.shot("preview_25")

    _hover(bar, 0.75)
    d.wait_until(lambda: label.preview is not first, "another picture at 75%")
    d.check("another time, another picture", label.preview != first)
    d.shot("preview_75")

    # the mouse gone, the picture with it; and none with the setting off
    bar.mouse_left.emit()
    d.check("none once the mouse has left", label.preview is None)

    Settings().set("player/seek_preview", False)
    _hover(bar, 0.5)
    d.pump(1.0)
    d.check("none with the setting off", label.preview is None)
    d.check("the time is still shown", label.isVisible())
