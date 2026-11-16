"""Favourites moved in Manage Favourites into a folder picked (Move To),
whatever they are shown sorted by: videos and folders, with all a folder
holds."""

from datetime import datetime, timezone
from unittest.mock import Mock

import pytest

from gridplayer.dialogs.favourites import (
    ITEM_DEPTH,
    ManageFavouritesDialog,
    MoveToFolderDialog,
)
from gridplayer.models.favourites import FavouriteFolder, Favourites
from gridplayer.params.static import FavouritesSort
from tests.test_favourites import (
    _favourites,
    _tree_item,
    _video,
    undated,  # noqa: F401 (autouse here too)
)


def _picked(dialog, *items):
    dialog.tree.clearSelection()
    for item in items:
        item.setSelected(True)


@pytest.fixture
def moving_into(monkeypatch):
    """Move To answered: the folder at this place in the tree, as found
    when asked; what it was offered kept."""

    asked = Mock()

    def answer(path):
        def ask(parent, folders, selected=None):
            asked(folders=folders, selected=selected)
            return _tree_item(parent, *path)

        monkeypatch.setattr(MoveToFolderDialog, "ask", ask)
        return asked

    return answer


class TestMovingThem:
    def test_a_video_into_a_folder(self, moving_into):
        dialog = ManageFavouritesDialog(_favourites())
        moving_into((2,))  # "Empty"
        _picked(dialog, _tree_item(dialog, 0))

        dialog.move_selected()

        favourites = dialog.favourites()
        assert [item.name for item in favourites.root] == ["Music", "Empty"]
        assert [item.name for item in favourites.items_at((1,))] == ["Top"]

    def test_a_folder_with_all_it_holds(self, moving_into):
        dialog = ManageFavouritesDialog(_favourites())
        moving_into((2,))
        _picked(dialog, _tree_item(dialog, 1))

        dialog.move_selected()

        favourites = dialog.favourites()
        assert favourites.folders() == [
            ((), []),
            ((1,), ["Empty"]),
            ((1, 0), ["Empty", "Music"]),
            ((1, 0, 1), ["Empty", "Music", "Live"]),
        ]
        assert favourites.items_at((1, 0, 1))[0].name == "Gig"

    def test_out_to_the_top(self, moving_into):
        dialog = ManageFavouritesDialog(_favourites())
        moving_into(())
        _picked(dialog, _tree_item(dialog, 1, 1, 0))  # "Gig"

        dialog.move_selected()

        favourites = dialog.favourites()
        assert [item.name for item in favourites.root] == [
            "Top",
            "Music",
            "Empty",
            "Gig",
        ]
        assert favourites.items_at((1, 1)) == []

    def test_several_at_once_in_the_order_shown(self, moving_into):
        dialog = ManageFavouritesDialog(_favourites())
        moving_into((2,))
        # picked from the bottom up
        _picked(dialog, _tree_item(dialog, 1, 1, 0), _tree_item(dialog, 0))

        dialog.move_selected()

        favourites = dialog.favourites()
        assert [v.name for v in favourites.items_at((1,))] == ["Top", "Gig"]

    def test_one_within_a_folder_moved_goes_with_it(self, moving_into):
        dialog = ManageFavouritesDialog(_favourites())
        moving_into((2,))
        _picked(dialog, _tree_item(dialog, 1), _tree_item(dialog, 1, 0))

        dialog.move_selected()

        moved = dialog.favourites().items_at((1, 0))
        assert [item.name for item in moved] == ["Song", "Live"]

    def test_at_the_end_of_the_folders_own(self, moving_into):
        favourites = _favourites()
        favourites.root[1].items.append(_video("Last"))
        dialog = ManageFavouritesDialog(favourites)
        moving_into((1,))
        _picked(dialog, _tree_item(dialog, 0))

        dialog.move_selected()

        assert [item.name for item in dialog.favourites().items_at((0,))] == [
            "Song",
            "Live",
            "Last",
            "Top",
        ]

    def test_still_picked_once_moved(self, moving_into):
        dialog = ManageFavouritesDialog(_favourites())
        moving_into((2,))
        top = _tree_item(dialog, 0)
        _picked(dialog, top)

        dialog.move_selected()

        assert dialog.tree.selectedItems() == [top]
        assert top.parent().isExpanded()

    def test_nothing_when_thought_better_of(self, monkeypatch):
        monkeypatch.setattr(MoveToFolderDialog, "ask", lambda *_a, **_k: None)
        dialog = ManageFavouritesDialog(_favourites())
        _picked(dialog, _tree_item(dialog, 0))

        dialog.move_selected()

        assert dialog.favourites() == _favourites()


class TestWhereTo:
    def test_every_folder_offered_but_those_moved(self, moving_into):
        dialog = ManageFavouritesDialog(_favourites())
        asked = moving_into(())
        _picked(dialog, _tree_item(dialog, 1))  # "Music", and "Live" in it

        dialog.move_selected()

        folders = asked.call_args.kwargs["folders"]
        assert [(depth, title) for depth, title, _ in folders] == [
            (0, "Favourites"),
            (1, "Empty"),
        ]

    def test_where_they_are_offered_first(self, moving_into):
        dialog = ManageFavouritesDialog(_favourites())
        asked = moving_into(())
        live = _tree_item(dialog, 1, 1)
        _picked(dialog, _tree_item(dialog, 1, 1, 0))

        dialog.move_selected()

        assert asked.call_args.kwargs["selected"] is live

    def test_the_window_picks_what_it_is_given(self):
        dialog = ManageFavouritesDialog(_favourites())
        empty = _tree_item(dialog, 2)
        folders = dialog._folders_to_move_into([])

        move_to = MoveToFolderDialog(folders=folders, selected=empty)

        box = move_to.folder
        assert [
            (box.itemData(i, ITEM_DEPTH), box.itemText(i)) for i in range(box.count())
        ] == [(0, "Favourites"), (1, "Music"), (2, "Live"), (1, "Empty")]
        assert move_to.selected_folder is empty

    def test_button_only_with_one_picked(self):
        dialog = ManageFavouritesDialog(_favourites())
        assert not dialog.move_button.isEnabled()

        _picked(dialog, _tree_item(dialog, 0))

        assert dialog.move_button.isEnabled()


def _at(day):
    return datetime(2026, 1, day, tzinfo=timezone.utc)


class TestWhileSorted:
    def test_moved_while_sorted_by_name(self, moving_into):
        favourites = Favourites(
            [
                _video("Zed").model_copy(update={"added": _at(1)}),
                FavouriteFolder(name="Box", items=[_video("Alpha")], added=_at(2)),
            ]
        )
        dialog = ManageFavouritesDialog(favourites)
        dialog.sort_by(FavouritesSort.NAME)
        # shown: Box (Alpha), Zed
        zed = _tree_item(dialog, 1)
        moving_into((0,))
        _picked(dialog, zed)

        dialog.move_selected()

        box = _tree_item(dialog, 0)
        assert [box.child(i).text(0) for i in range(box.childCount())] == [
            "Alpha",
            "Zed",
        ]
        # kept in their own order: at the end of the folder's
        assert [v.name for v in dialog.favourites().items_at((0,))] == [
            "Alpha",
            "Zed",
        ]

    def test_moved_while_sorted_by_date(self, moving_into):
        favourites = Favourites(
            [
                FavouriteFolder(name="Old", added=_at(1)),
                _video("Newest").model_copy(update={"added": _at(9)}),
                FavouriteFolder(name="Mid", items=[], added=_at(5)),
            ]
        )
        dialog = ManageFavouritesDialog(favourites)
        dialog.sort_by(FavouritesSort.ADDED_DESC)
        # shown: Newest, Mid, Old
        assert _tree_item(dialog, 0).text(0) == "Newest"
        moving_into((2,))  # "Old"
        _picked(dialog, _tree_item(dialog, 0))

        dialog.move_selected()

        assert dialog.favourites().folders()[1:] == [
            ((0,), ["Old"]),
            ((1,), ["Mid"]),
        ]
        assert dialog.favourites().items_at((0,))[0].name == "Newest"


def test_the_same_folder_left_as_it_is(moving_into):
    dialog = ManageFavouritesDialog(_favourites())
    moving_into((1,))
    _picked(dialog, _tree_item(dialog, 1, 0))  # "Song", in "Music"

    dialog.move_selected()

    assert dialog.favourites() == _favourites()


def test_one_at_the_top_moved_to_the_top_left_as_it_is(moving_into):
    dialog = ManageFavouritesDialog(_favourites())
    moving_into(())
    _picked(dialog, _tree_item(dialog, 0))

    dialog.move_selected()

    assert dialog.favourites() == _favourites()
