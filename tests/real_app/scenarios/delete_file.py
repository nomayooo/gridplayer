"""Files deleted for good from the player: kept when thought better of, then
gone, with their cells, while they were playing, one on its own and two
picked out (Ctrl+Click) together; and let go of by everything that had them
open, the seek preview's process too, for their space to be freed.

Copies of the clips are deleted, never the media themselves.
"""


def _holders(path):
    """The processes with the file open still, deleted or not (Linux)."""

    from pathlib import Path

    holders = []
    for process in Path("/proc").iterdir():
        if not process.name.isdigit():
            continue
        try:
            fds = list((process / "fd").iterdir())
        except OSError:
            continue
        for fd in fds:
            try:
                target = str(fd.readlink())
            except OSError:
                continue
            if target.startswith(str(path)):
                holders.append(process.name)
    return holders


def _answer(d, which):
    def answer(box):
        from PyQt5.QtWidgets import QMessageBox

        d.check("asked first", "Permanently delete" in box.text(), box.text())
        box.button(QMessageBox.Yes if which == "yes" else QMessageBox.No).click()

    return answer


def scenario(d):
    import shutil

    folder = d.out / "to-delete"
    folder.mkdir(exist_ok=True)

    copies = []
    for clip in d.media.clips[:3]:
        copy = folder / clip.name
        shutil.copy(clip, copy)
        copies.append(copy)

    d.open(*copies)
    a = d.wait_for_cell("a.mp4")
    b = d.wait_for_cell("b.mp4")
    c = d.wait_for_cell("c.mp4")
    for cell in (a, b, c):
        d.wait_until(lambda cell=cell: cell.is_playable, f"{cell.title} plays")

    # its seek bar hovered: the preview's process has it open as well
    previewed = []
    d.ctx.seek_preview.request(copies[0], 5_000, lambda *got: previewed.append(got))
    d.wait_until(lambda: previewed, "a preview read", timeout=15)

    d.through_modal(lambda: d.act(a, "Delete File"), "not sure", _answer(d, "no"))
    d.check("kept when not sure", copies[0].exists() and a in d.cells)

    d.through_modal(lambda: d.act(a, "Delete File"), "sure", _answer(d, "yes"))
    d.wait_until(lambda: len(d.cells) == 2, "its cell closed")
    d.wait_until(lambda: not copies[0].exists(), "the file gone")
    d.check("let go of by all", _holders(copies[0]) == [], _holders(copies[0]))
    d.check("the others kept", copies[1].exists() and copies[2].exists())

    d.act(b, "Select")
    d.act(c, "Select")
    d.through_modal(lambda: d.act(b, "Delete File"), "both", _answer(d, "yes"))
    d.wait_until(lambda: len(d.cells) == 0, "both cells closed")
    d.wait_until(
        lambda: not copies[1].exists() and not copies[2].exists(), "both files gone"
    )
    d.check("the media themselves kept", all(c.exists() for c in d.media.clips[:3]))
