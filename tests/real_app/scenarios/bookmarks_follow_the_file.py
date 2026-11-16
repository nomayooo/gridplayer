"""Bookmarks following their file when it is moved: a copy of a clip marked
with M, closed, renamed into another folder, and opened from there: its
bookmarks are there, and kept in the settings by where it is now, none left
where it was."""

import os
import shutil
from pathlib import Path


def scenario(d):
    from PyQt5.QtCore import Qt
    from PyQt5.QtTest import QTest
    from PyQt5.QtWidgets import QApplication

    from gridplayer.settings import Settings
    from gridplayer.utils.bookmarks import file_key

    # a copy of its own, to move about
    work = Path(os.environ["GP_USER_DATA_DIR"]).parent / "moved-media"
    shutil.rmtree(work, ignore_errors=True)
    (work / "before").mkdir(parents=True)
    (work / "after").mkdir()
    film = work / "before" / "film.mp4"
    shutil.copyfile(d.media.clips[0], film)

    d.open(film)
    a = d.wait_for_cell("film.mp4")
    d.wait_until(lambda: a.is_playable, "plays")
    d.run(a, "active", "set_pause", True)
    d.ctx.active_block = a

    d.run(a, "active", "seek", 4_000)
    d.wait_until(lambda: abs(a.time - 4_000) < 400, "at 4s")
    QTest.keyClick(QApplication.focusWidget() or d.player, Qt.Key_M)
    d.pump()
    marked = [b.time_ms for b in a.bookmarks]
    d.check("one marked", len(marked) == 1, marked)

    d.act(a, "Close")
    d.wait_until(lambda: not d.cells, "closed")
    d.ctx.bookmarks.clear()

    moved = film.rename(work / "after" / "renamed.mp4")

    d.open(moved)
    again = d.wait_for_cell("renamed.mp4")
    d.wait_until(lambda: again.is_playable, "plays from where it was moved to")
    d.wait_until(
        lambda: [b.time_ms for b in again.bookmarks] == marked,
        "its bookmarks followed it",
    )

    kept = Settings().sync_get("bookmarks/remembered").root
    d.check(
        "kept where it is now, none where it was",
        list(kept) == [file_key(moved)],
        list(kept),
    )
