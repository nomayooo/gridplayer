"""A click on a video that wobbles a few pixels is a click, and a drag far
enough is a drag, on any video of the grid: not only on the one at the
window's corner, where a cell's own coordinates and the window's agree."""


def scenario(d):
    from PyQt5.QtCore import QEvent, QPoint, QPointF, Qt
    from PyQt5.QtGui import QCursor, QMouseEvent
    from PyQt5.QtWidgets import QApplication

    clips = d.media.clips[:2]
    d.open(*clips)
    cells = [d.wait_for_cell(clip.name) for clip in clips]
    for cell in cells:
        d.wait_until(lambda cell=cell: cell.is_playable, "plays")
    d.player.resize(1000, 400)
    d.pump()

    dnd = d.player._managers_inst["drag_n_drop"]

    def pressed_and_moved(cell, by):
        """Pressed at the cell's middle and moved by this much, as the
        mouse would be, to the widget under it: whether a drag began."""

        dnd._drag_start_position = None
        centre = cell.mapToGlobal(cell.rect().center())
        QCursor.setPos(centre)
        d.pump()
        target = QApplication.widgetAt(centre) or cell

        def send(kind, at, buttons):
            QApplication.sendEvent(
                target,
                QMouseEvent(
                    kind,
                    QPointF(target.mapFromGlobal(at)),
                    QPointF(at),
                    Qt.LeftButton,
                    buttons,
                    Qt.NoModifier,
                ),
            )

        send(QEvent.MouseButtonPress, centre, Qt.LeftButton)
        send(QEvent.MouseMove, centre + by, Qt.LeftButton)
        began = dnd._is_fake_drag_active
        if began:
            dnd._cancel_fake_drag()
        else:
            send(QEvent.MouseButtonRelease, centre + by, Qt.NoButton)
        d.pump()
        return began

    for cell in cells:
        name = cell.video_params.uri.name
        offset = cell.mapTo(d.player, QPoint(0, 0))
        d.note(f"{name} at {offset.x()}, {offset.y()} in the window")

        began = pressed_and_moved(cell, QPoint(6, 3))
        d.check(f"{name}: a wobble is a click", not began, began)

        began = pressed_and_moved(cell, QPoint(40, 0))
        d.check(f"{name}: far enough, a drag", began, began)
