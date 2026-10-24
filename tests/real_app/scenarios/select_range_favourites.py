"""Cells picked out with the mouse, Ctrl+Click one and Shift+Click another
for those between too, Shift+Click nearer shrinking the range again as a
file manager does, and the ones picked made favourites all at once, into a
folder, by Add to Favourites.
"""


def _click(d, cell, modifier):
    from PyQt5.QtCore import QPoint, Qt
    from PyQt5.QtTest import QTest

    # the middle of the picture, above the controls
    where = QPoint(cell.width() // 2, cell.height() // 3)
    d.ctx.active_block = cell
    QTest.mouseClick(cell, Qt.LeftButton, modifier, where)
    d.pump()


def scenario(d):
    from PyQt5.QtCore import Qt

    from gridplayer.models.favourites import Favourites
    from gridplayer.settings import Settings

    Settings().set("favourites", Favourites())

    clips = d.media.clips[:3]
    d.open(*clips)
    cells = [d.wait_for_cell(c.name) for c in clips]
    for cell in cells:
        d.wait_until(lambda cell=cell: cell.is_playable, f"{cell.title} plays")
    a, b, c = cells

    _click(d, a, Qt.ControlModifier)
    d.check("a picked", [x.is_selected for x in cells] == [True, False, False])

    _click(d, c, Qt.ShiftModifier)
    d.check("a to c picked", [x.is_selected for x in cells] == [True, True, True])

    # as a file manager: from a again, to b now, c let go
    _click(d, b, Qt.ShiftModifier)
    d.check("a to b only", [x.is_selected for x in cells] == [True, True, False])

    _click(d, c, Qt.ShiftModifier)
    d.check("a to c again", [x.is_selected for x in cells] == [True, True, True])
    d.shot("three picked")

    item = d.ctx.actions["Add to Favourites"]
    d.check(
        "offered for them",
        item.title == "Add Selected to Favourites...",
        item.title,
    )

    def into_new_folder(window):
        d.check(
            "titled so",
            window.windowTitle() == "Add Selected to Favourites",
            window.windowTitle(),
        )
        d.check("for three", "3" in window.count_note.text(), window.count_note.text())
        window.accept()

    d.through_modal(
        lambda: d.act(b, "Add to Favourites"), "add selected", into_new_folder
    )

    kept = Settings().get("favourites").root
    names = [v.name for v in kept]
    d.check("all three kept", len(kept) == 3, names)
    d.check(
        "their files",
        [str(v.path) for v in kept] == [str(x) for x in clips],
        [str(v.path) for v in kept],
    )
