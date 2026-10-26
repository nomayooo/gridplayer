"""Manage Favourites sorted by name and by when each was added, folders and
videos together, each folder's own: one added in the player dated as it is
added, one renamed in its place while sorted by name moved to its new name,
the sort kept for the next time, and their own order kept all the same.
"""


def scenario(d):
    from datetime import datetime, timezone

    from PyQt5.QtCore import Qt
    from PyQt5.QtTest import QTest
    from PyQt5.QtWidgets import QApplication

    from gridplayer.models.favourites import FavouriteFolder, Favourites
    from gridplayer.params.static import FavouritesSort
    from gridplayer.settings import Settings

    a_clip, b_clip = d.media.clips[:2]

    def at(day):
        return datetime(2026, 10, day, 12, tzinfo=timezone.utc)

    Settings().set(
        "favourites",
        Favourites.model_validate(
            [
                {"kind": "video", "name": "b", "path": str(a_clip), "added": at(5)},
                FavouriteFolder(name="Zed", added=at(2)).model_dump(),
                {"kind": "video", "name": "Apple", "path": str(b_clip), "added": at(8)},
            ]
        ),
    )
    Settings().set("favourites/sort", FavouritesSort.OWN)

    d.open(a_clip)
    a = d.wait_for_cell(a_clip.name)
    d.wait_until(lambda: a.is_playable, "plays")

    def add_named_c(window):
        window.name.setText("c")
        window.accept()

    d.through_modal(lambda: d.act(a, "Add to Favourites"), "add c", add_named_c)

    kept = Settings().get("favourites").root
    d.check("c added now, dated", kept[-1].added is not None, str(kept[-1].added))

    def shown(window):
        tree = window.tree
        return [tree.topLevelItem(i).text(0) for i in range(tree.topLevelItemCount())]

    def pick(window, sort):
        window.sort_box.setCurrentIndex(window.sort_box.findData(sort))
        d.pump()

    def sort_them(window):
        d.check("their own order", shown(window) == ["b", "Zed", "Apple", "c"])

        pick(window, FavouritesSort.NAME)
        d.check("by name", shown(window) == ["Apple", "b", "c", "Zed"], shown(window))

        pick(window, FavouritesSort.ADDED_DESC)
        d.check(
            "newest first", shown(window) == ["c", "Apple", "b", "Zed"], shown(window)
        )
        d.shot("newest first", window)

        pick(window, FavouritesSort.NAME)

        # renamed in place, as a person does: F2, a name typed, Enter
        apple = window.tree.topLevelItem(0)
        window.tree.setCurrentItem(apple)
        window.tree.setFocus()
        QTest.keyClick(window.tree, Qt.Key_F2)
        d.pump()
        editor = QApplication.focusWidget()
        editor.selectAll()
        QTest.keyClicks(editor, "zz Apple")
        QTest.keyClick(editor, Qt.Key_Return)
        d.wait_until(lambda: shown(window)[-1] == "zz Apple", "moved to its name")
        d.check("renamed in its place", shown(window) == ["b", "c", "Zed", "zz Apple"])
        d.shot("renamed", window)

        window.accept()

    d.through_modal(lambda: d.act(a, "Manage Favourites"), "sort", sort_them)

    kept = Settings().get("favourites").root
    d.check(
        "kept in their own order",
        [f.name for f in kept] == ["b", "Zed", "zz Apple", "c"],
        [f.name for f in kept],
    )
    d.check("the sort kept", Settings().get("favourites/sort") == FavouritesSort.NAME)

    def sorted_again(window):
        d.check("sorted so again", shown(window) == ["b", "c", "Zed", "zz Apple"])
        window.reject()

    d.through_modal(lambda: d.act(a, "Manage Favourites"), "again", sorted_again)
