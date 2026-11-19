"""Duplicate (Alt+D): a copy of the cell put right after it in the grid, at
where the video was, the other cells moving along."""


def scenario(d):
    from PyQt5.QtCore import Qt
    from PyQt5.QtTest import QTest
    from PyQt5.QtWidgets import QApplication

    clips = d.media.clips[:2]
    d.open(*clips)
    a = d.wait_for_cell("a.mp4")
    d.wait_for_cell("b.mp4")
    d.wait_until(lambda: a.is_playable, "plays")
    d.run(a, "active", "set_pause", True)
    d.run(a, "active", "seek", 5_000)
    d.wait_until(lambda: abs(a.time - 5_000) < 400, "at 5s")
    d.ctx.active_block = a

    QTest.keyClick(QApplication.focusWidget() or d.player, Qt.Key_D, Qt.AltModifier)
    d.pump()

    d.wait_until(lambda: len(d.cells) == 3, "a copy added")

    def order():
        blocks = d.ctx.video_blocks.blocks_for_ids(d.ctx.commands.layout_order())
        return [b.video_params.uri_name for b in blocks]

    d.check("right after it", order() == ["a.mp4", "a.mp4", "b.mp4"], order())

    blocks = d.ctx.video_blocks.blocks_for_ids(d.ctx.commands.layout_order())
    copy = blocks[1]
    d.check("a cell of its own", copy is not a)
    d.wait_until(lambda: copy.is_playable, "the copy plays")
    d.wait_until(lambda: abs(copy.time - 5_000) < 600, "at where it was")
