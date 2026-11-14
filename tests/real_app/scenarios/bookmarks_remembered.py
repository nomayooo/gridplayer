"""Bookmarks found again whenever their file is opened: marked with M, the
cell closed and the playlist with it, then the file opened again on its own,
its bookmarks are there, on the bar too; and they are in the settings, for
the next time the player starts."""


def _at(d, a, ms, what):
    d.run(a, "active", "seek", ms)
    d.wait_until(lambda: abs(a.time - ms) < 400, what)


def scenario(d):
    from PyQt5.QtCore import Qt
    from PyQt5.QtTest import QTest
    from PyQt5.QtWidgets import QApplication

    from gridplayer.models.seek_mark import SeekMarkKind
    from gridplayer.settings import Settings
    from gridplayer.utils.bookmarks import file_key

    clip = d.media.clips[0]
    d.open(clip)
    a = d.wait_for_cell("a.mp4")
    d.wait_until(lambda: a.is_playable, "plays")
    d.run(a, "active", "set_pause", True)
    d.ctx.active_block = a

    for ms in (3_000, 9_000):
        _at(d, a, ms, f"at {ms // 1000}s")
        QTest.keyClick(QApplication.focusWidget() or d.player, Qt.Key_M)
        d.pump()

    marked = [b.time_ms for b in a.bookmarks]
    d.check("two marked", len(marked) == 2, marked)

    kept = Settings().sync_get("bookmarks/remembered").root.get(file_key(clip))
    d.check(
        "kept in the settings",
        kept is not None and [b.time_ms for b in kept.bookmarks] == marked,
        None if kept is None else [b.time_ms for b in kept.bookmarks],
    )

    # gone: the cell, and the playlist's own bookmarks with it
    d.act(a, "Close")
    d.wait_until(lambda: not d.cells, "closed")
    d.ctx.bookmarks.clear()

    d.open(clip)
    again = d.wait_for_cell("a.mp4")
    d.wait_until(lambda: again.is_playable, "plays again")
    d.wait_until(
        lambda: [b.time_ms for b in again.bookmarks] == marked,
        "its bookmarks found again",
    )
    bar_marks = [
        m.time_ms
        for m in again.overlay.progress_bar.marks
        if m.kind == SeekMarkKind.BOOKMARK
    ]
    d.check("on the bar too", bar_marks == marked, bar_marks)
