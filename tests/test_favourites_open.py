"""Opening from Manage Favourites: several folders picked, each in a window
of its own, the videos picked into this one; and Open and Close, which
opens them and closes the window as OK does."""

from gridplayer.dialogs.favourites import ManageFavouritesDialog
from gridplayer.models.favourites import FavouriteFolder, Favourites
from tests.test_favourites import (
    _tree_item,
    _video,
    undated,  # noqa: F401 (autouse here too)
)


def _favourites():
    """Two folders, one with a folder in it; a video at the top."""

    return Favourites(
        [
            _video("Loose"),
            FavouriteFolder(
                name="One",
                items=[
                    _video("a"),
                    _video("b"),
                    FavouriteFolder(name="Inner", items=[_video("i")]),
                ],
            ),
            FavouriteFolder(name="Two", items=[_video("c")]),
            FavouriteFolder(name="Empty"),
        ]
    )


def _opened(dialog):
    opened = []
    dialog.open_requested.connect(
        lambda here, apart: opened.append(
            ([v.name for v in here], [[v.name for v in w] for w in apart])
        )
    )
    return opened


def _picked(dialog, *paths):
    for path in paths:
        _tree_item(dialog, *path).setSelected(True)


class TestSeveralFolders:
    def test_each_in_a_window_of_its_own(self):
        dialog = ManageFavouritesDialog(_favourites())
        opened = _opened(dialog)
        _picked(dialog, (1,), (2,))

        dialog.open_selected()

        # One's own, then the folder within it, then Two's
        assert opened == [([], [["a", "b"], ["i"], ["c"]])]

    def test_the_videos_picked_with_them_into_this_one(self):
        dialog = ManageFavouritesDialog(_favourites())
        opened = _opened(dialog)
        _picked(dialog, (0,), (1,), (2,), (1, 1))

        dialog.open_selected()

        # "b", within One picked, goes with it
        assert opened == [(["Loose"], [["a", "b"], ["i"], ["c"]])]

    def test_an_empty_one_opens_no_window(self):
        dialog = ManageFavouritesDialog(_favourites())
        opened = _opened(dialog)
        _picked(dialog, (2,), (3,))

        dialog.open_selected()

        assert opened == [([], [["c"]])]

    def test_one_within_another_picked_is_not_a_second(self):
        dialog = ManageFavouritesDialog(_favourites())
        opened = _opened(dialog)
        _picked(dialog, (1,), (1, 2))

        dialog.open_selected()

        # One alone: its own here, as ever
        assert opened == [(["a", "b"], [["i"]])]

    def test_one_alone_still_opens_its_own_here(self):
        dialog = ManageFavouritesDialog(_favourites())
        opened = _opened(dialog)
        _picked(dialog, (2,), (0,))

        dialog.open_selected()

        assert opened == [(["Loose", "c"], [])]


def test_videos_alone_into_this_one():
    dialog = ManageFavouritesDialog(_favourites())
    opened = _opened(dialog)
    _picked(dialog, (0,), (1, 0), (2, 0))

    dialog.open_selected()

    assert opened == [(["Loose", "a", "c"], [])]


class TestOpenAndClose:
    def test_opened_then_closed_as_ok(self):
        dialog = ManageFavouritesDialog(_favourites())
        opened = _opened(dialog)
        _picked(dialog, (1, 0))

        dialog.open_close_button.click()

        assert opened == [(["a"], [])]
        assert dialog.result() == ManageFavouritesDialog.Accepted

    def test_changes_kept_as_on_ok(self, monkeypatch):
        def picked_and_renamed(self):
            _tree_item(self, 0).setText(0, "Renamed")
            _tree_item(self, 0).setSelected(True)
            self.open_close_button.click()
            return self.result()

        monkeypatch.setattr(ManageFavouritesDialog, "exec", picked_and_renamed)
        opened = []

        edited = ManageFavouritesDialog.edit(
            None,
            _favourites(),
            on_open=lambda here, apart: opened.append([v.name for v in here]),
        )

        assert opened == [["Renamed"]]
        assert edited.root[0].name == "Renamed"

    def test_only_with_something_to_open(self):
        dialog = ManageFavouritesDialog(_favourites())

        assert not dialog.open_close_button.isEnabled()

        _picked(dialog, (3,))
        assert not dialog.open_close_button.isEnabled()

        _picked(dialog, (2,))
        assert dialog.open_close_button.isEnabled()

    def test_beside_ok(self):
        dialog = ManageFavouritesDialog(_favourites())
        box = dialog.open_close_button.parent()

        assert dialog.open_close_button in box.buttons()
