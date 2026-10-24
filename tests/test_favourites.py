"""Favourite videos in folders, as a web browser keeps its favourites: the
model they are kept as, the menu they are opened from, making them from the
active video, the window they are put in order in, and their opening into
the grid with their A-B loops.

The real-app scenario favourites drives them in the player itself.
"""

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, Mock

import pytest
from PyQt5.QtWidgets import QWidget

from gridplayer.dialogs import favourites as dialogs
from gridplayer.dialogs.favourites import AddFavouriteDialog, ManageFavouritesDialog
from gridplayer.models.favourites import (
    FavouriteFolder,
    Favourites,
    FavouriteVideo,
    videos_in,
)
from gridplayer.player.managers import favourites as manager_module
from gridplayer.player.managers.add_videos import AddVideosManager
from gridplayer.player.managers.favourites import FavouritesManager

HERE = Path(__file__).resolve()
GONE = HERE.parent / "no such video.mp4"


def _video(name="Clip", path=HERE, loops=(), loop_start=None):
    return FavouriteVideo(
        name=name, path=path, loops=list(loops), loop_start=loop_start
    )


def _favourites():
    """Top: a video, a folder of a video and a folder within, an empty
    folder."""

    return Favourites(
        [
            _video("Top", loops=[(1000, 2000)]),
            FavouriteFolder(
                name="Music",
                items=[
                    _video("Song", loops=[(0, 500), (700, None)], loop_start=900),
                    FavouriteFolder(name="Live", items=[_video("Gig")]),
                ],
            ),
            FavouriteFolder(name="Empty"),
        ]
    )


class TestTheModel:
    def test_kept_as_json_and_read_back(self):
        favourites = _favourites()

        read = Favourites.model_validate_json(favourites.model_dump_json())

        assert read == favourites
        assert read.items_at((1,))[0].loops == [(0, 500), (700, None)]
        assert read.items_at((1,))[0].loop_start == 900

    def test_kept_before_loop_starts_were_read_without_one(self):
        read = Favourites.model_validate_json(
            '[{"kind": "video", "name": "Old", "path": "/v.mp4", "loops": []}]'
        )

        assert read.root[0].loop_start is None

    def test_a_folder_by_where_it_is(self):
        favourites = _favourites()

        assert [i.name for i in favourites.items_at(())] == ["Top", "Music", "Empty"]
        assert [i.name for i in favourites.items_at((1, 1))] == ["Gig"]

    @pytest.mark.parametrize("path", [(0,), (9,), (1, 0)])
    def test_no_folder_there(self, path):
        with pytest.raises(KeyError):
            _favourites().items_at(path)

    def test_added_at_the_end_of_its_folder(self):
        favourites = _favourites()

        favourites.add((1, 1), _video("Encore"))

        assert [i.name for i in favourites.items_at((1, 1))] == ["Gig", "Encore"]

    def test_every_folder_top_first_in_the_order_shown(self):
        assert _favourites().folders() == [
            ((), []),
            ((1,), ["Music"]),
            ((1, 1), ["Music", "Live"]),
            ((2,), ["Empty"]),
        ]

    def test_a_folders_videos_are_its_own_not_its_folders(self):
        assert [v.name for v in videos_in(_favourites().items_at((1,)))] == ["Song"]

    def test_none_is_nothing(self):
        assert not Favourites()
        assert _favourites()


@pytest.fixture
def stored(monkeypatch):
    """The settings the favourites are kept in, a dict of their own."""

    values = {"favourites": _favourites()}

    monkeypatch.setattr(
        manager_module,
        "Settings",
        lambda: SimpleNamespace(get=values.get, set=values.__setitem__),
    )

    return values


def _manager(active=None):
    ctx = SimpleNamespace(active_block=active, commands=MagicMock())

    return FavouritesManager(context=ctx)


class TestTheMenu:
    def test_the_top_lists_folders_and_videos(self, stored):
        menu = _manager().menu_generator_favourites()

        assert [item["title"] for item in menu] == ["Top", "Music", "Empty"]
        assert menu[0]["func"] == ("open_favourite", stored["favourites"].root[0])
        assert menu[1]["menu_generator"] == ("menu_generator_favourites_folder", (1,))

    def test_a_folder_with_videos_ends_with_open_all(self, stored):
        menu = _manager().menu_generator_favourites_folder((1,))

        assert [i if i == "---" else i["title"] for i in menu] == [
            "Song",
            "Live",
            "---",
            "Open All",
        ]
        assert menu[-1]["func"] == ("open_favourites_folder", (1,))

    def test_a_folder_of_folders_alone_has_no_open_all(self, stored):
        stored["favourites"] = Favourites(
            [FavouriteFolder(name="A", items=[FavouriteFolder(name="B")])]
        )

        menu = _manager().menu_generator_favourites_folder((0,))

        assert [i["title"] for i in menu] == ["B"]

    def test_an_empty_folder_is_shown_greyed_out(self, stored):
        manager = _manager()

        assert manager.menu_generator_favourites()[2]["enable_if"] == (
            "is_favourites_folder_full",
            (2,),
        )
        assert not manager.is_favourites_folder_full((2,))
        assert manager.is_favourites_folder_full((1,))

    def test_a_long_name_is_cut_short(self, stored):
        stored["favourites"] = Favourites([_video("x" * 200)])

        (item,) = _manager().menu_generator_favourites()

        assert "..." in item["title"]
        assert len(item["title"]) < manager_module.MENU_NAME_MAX_LENGTH + 5

    def test_a_folder_gone_since_is_empty(self, stored):
        assert _manager().menu_generator_favourites_folder((7,)) == []


class TestOpening:
    def test_a_favourite_goes_into_the_grid(self, stored):
        manager = _manager()
        favourite = stored["favourites"].root[0]

        manager.cmd_open_favourite(favourite)

        manager._ctx.commands.add_favourite_videos.assert_called_once_with([favourite])

    def test_open_all_opens_the_folders_own_videos(self, stored):
        manager = _manager()

        manager.cmd_open_favourites_folder((1,))

        ((videos,), _) = manager._ctx.commands.add_favourite_videos.call_args
        assert [v.name for v in videos] == ["Song"]


@pytest.fixture
def adder():
    parent = QWidget()
    ctx = SimpleNamespace(
        commands=MagicMock(),
        video_blocks=SimpleNamespace(by_video_id=lambda _id: object()),
    )

    manager = AddVideosManager(context=ctx, parent=parent)
    manager.kept_parent = parent

    manager.added = []
    manager.videos_added.connect(manager.added.append)
    manager.errors = []
    manager.error.connect(manager.errors.append)

    return manager


class TestIntoTheGrid:
    def test_each_in_a_cell_of_its_own_with_its_loops(self, adder):
        adder.add_favourite_videos(
            [_video(loops=[(1000, 2000), (3000, None)]), _video()]
        )

        ((first, second),) = adder.added
        assert first.uri == HERE
        assert first.loops == [(1000, 2000), (3000, None)]
        assert first.loop_start is None
        assert second.loops == []
        adder._ctx.commands.add_recent_uris.assert_called_once_with([HERE, HERE])

    def test_with_a_loop_begun_and_not_finished(self, adder):
        adder.add_favourite_videos([_video(loops=[(1000, 2000)], loop_start=5000)])

        ((video,),) = adder.added
        assert video.loops == [(1000, 2000)]
        assert video.loop_start == 5000
        assert video.current_position == 5000

    def test_a_file_gone_is_said_and_the_rest_opened(self, adder):
        adder.add_favourite_videos([_video(path=GONE), _video()])

        assert [len(batch) for batch in adder.added] == [1]
        (error,) = adder.errors
        assert str(GONE) in error

    def test_nothing_opened_when_none_are_there(self, adder):
        adder.add_favourite_videos([_video(path=GONE)])

        assert adder.added == []
        adder._ctx.commands.add_recent_uris.assert_not_called()


def _block(uri=HERE, title="Shown title", loops=(), loop_start=None):
    return SimpleNamespace(
        is_local_file=isinstance(uri, Path),
        title=title,
        video_params=SimpleNamespace(uri=uri, loops=list(loops), loop_start=loop_start),
    )


class TestMakingOne:
    def test_the_active_video_with_its_loops_into_the_folder_picked(
        self, stored, monkeypatch
    ):
        asked = Mock(return_value=(stored["favourites"], (1, 1), "My clip"))
        monkeypatch.setattr(manager_module.AddFavouriteDialog, "ask", asked)

        _manager(active=_block(loops=[(500, 900)])).cmd_add_to_favourites()

        assert asked.call_args.kwargs["name"] == "Shown title"
        assert asked.call_args.kwargs["loops"] == 1
        added = stored["favourites"].items_at((1, 1))[-1]
        assert added == FavouriteVideo(name="My clip", path=HERE, loops=[(500, 900)])

    def test_a_loop_begun_and_not_finished_kept_too(self, stored, monkeypatch):
        asked = Mock(return_value=(stored["favourites"], (), "Begun"))
        monkeypatch.setattr(manager_module.AddFavouriteDialog, "ask", asked)

        _manager(active=_block(loop_start=12_000)).cmd_add_to_favourites()

        assert asked.call_args.kwargs["loops"] == 0
        assert asked.call_args.kwargs["loop_start"] == 12_000
        added = stored["favourites"].root[-1]
        assert (added.loops, added.loop_start) == ([], 12_000)

    def test_named_after_the_file_without_a_title(self, stored, monkeypatch):
        asked = Mock(return_value=None)
        monkeypatch.setattr(manager_module.AddFavouriteDialog, "ask", asked)

        _manager(active=_block(title=None)).cmd_add_to_favourites()

        assert asked.call_args.kwargs["name"] == HERE.stem

    def test_nothing_kept_when_thought_better_of(self, stored, monkeypatch):
        before = stored["favourites"].model_copy(deep=True)
        monkeypatch.setattr(
            manager_module.AddFavouriteDialog, "ask", Mock(return_value=None)
        )

        _manager(active=_block()).cmd_add_to_favourites()

        assert stored["favourites"] == before

    @pytest.mark.parametrize("active", [None, _block(uri="https://example.com/v")])
    def test_not_of_what_is_not_a_file(self, stored, monkeypatch, active):
        asked = Mock()
        monkeypatch.setattr(manager_module.AddFavouriteDialog, "ask", asked)

        _manager(active=active).cmd_add_to_favourites()

        asked.assert_not_called()

    def test_put_in_order_kept_on_ok(self, stored, monkeypatch):
        edited = Favourites([_video("Only")])
        monkeypatch.setattr(
            manager_module.ManageFavouritesDialog, "edit", Mock(return_value=edited)
        )

        _manager().cmd_manage_favourites()

        assert stored["favourites"] == edited

    def test_put_in_order_not_kept_on_cancel(self, stored, monkeypatch):
        before = stored["favourites"]
        monkeypatch.setattr(
            manager_module.ManageFavouritesDialog, "edit", Mock(return_value=None)
        )

        _manager().cmd_manage_favourites()

        assert stored["favourites"] is before


def _typed(monkeypatch, text):
    monkeypatch.setattr(
        dialogs.QCustomTextInput, "get_text", lambda *_args, **_kwargs: text
    )


class TestTheAddWindow:
    def test_every_folder_offered_the_top_first(self):
        dialog = AddFavouriteDialog(_favourites(), name="Clip", loops=0)

        assert [dialog.folder.itemData(i) for i in range(dialog.folder.count())] == [
            (),
            (1,),
            (1, 1),
            (2,),
        ]
        assert dialog.folder.itemText(2).strip() == "Live"
        assert dialog.selected_folder == ()

    def test_a_folder_made_is_picked_and_kept_only_in_its_copy(self, monkeypatch):
        favourites = _favourites()
        dialog = AddFavouriteDialog(favourites, name="Clip", loops=0)
        dialog.fill_folders(selected=(1,))
        _typed(monkeypatch, "  New one ")

        dialog.new_folder()

        assert dialog.selected_folder == (1, 2)
        assert dialog.favourites.items_at((1, 2)) == []
        assert dialog.favourites.items_at((1,))[2].name == "New one"
        assert len(favourites.items_at((1,))) == 2

    def test_no_folder_made_on_cancel(self, monkeypatch):
        dialog = AddFavouriteDialog(_favourites(), name="Clip", loops=0)
        _typed(monkeypatch, "")

        dialog.new_folder()

        assert dialog.favourites == _favourites()

    def test_no_name_no_ok(self):
        dialog = AddFavouriteDialog(_favourites(), name="Clip", loops=0)

        dialog.name.setText("  ")

        assert not dialog.ok_button.isEnabled()

    def test_the_loops_kept_are_said(self):
        assert AddFavouriteDialog(Favourites(), name="C", loops=0).loops_note.isHidden()

        dialog = AddFavouriteDialog(Favourites(), name="C", loops=3)
        assert not dialog.loops_note.isHidden()
        assert "3" in dialog.loops_note.text()
        assert dialog.loop_start_note.isHidden()

    def test_a_loop_begun_is_said(self):
        dialog = AddFavouriteDialog(Favourites(), name="C", loops=0, loop_start=12_000)

        assert dialog.loops_note.isHidden()
        assert not dialog.loop_start_note.isHidden()
        assert "0:12.000" in dialog.loop_start_note.text()


def _tree_item(dialog, *path):
    item = dialog.tree.invisibleRootItem()

    for index in path:
        item = item.child(index)

    return item


class TestTheManageWindow:
    def test_as_it_was_given_back_untouched(self):
        assert ManageFavouritesDialog(_favourites()).favourites() == _favourites()

    def test_loops_and_a_loop_begun_are_shown(self):
        dialog = ManageFavouritesDialog(_favourites())

        assert _tree_item(dialog, 0).text(1) == "1"
        assert _tree_item(dialog, 1, 0).text(1) == "2, start at 0:00.900"
        assert _tree_item(dialog, 1, 1, 0).text(1) == ""

    def test_renamed(self):
        dialog = ManageFavouritesDialog(_favourites())

        _tree_item(dialog, 1).setText(0, "Songs")
        _tree_item(dialog, 1, 0).setText(0, "Tune")

        favourites = dialog.favourites()
        assert favourites.root[1].name == "Songs"
        assert favourites.items_at((1,))[0] == _video(
            "Tune", loops=[(0, 500), (700, None)], loop_start=900
        )

    def test_a_name_cleared_is_kept(self):
        dialog = ManageFavouritesDialog(_favourites())

        _tree_item(dialog, 0).setText(0, " ")

        assert dialog.favourites().root[0].name == "Top"

    def test_moved_into_a_folder_keeps_its_loops(self):
        dialog = ManageFavouritesDialog(_favourites())

        root = dialog.tree.invisibleRootItem()
        _tree_item(dialog, 2).addChild(root.takeChild(0))

        favourites = dialog.favourites()
        assert [i.name for i in favourites.root] == ["Music", "Empty"]
        assert favourites.items_at((1,)) == [_video("Top", loops=[(1000, 2000)])]

    def test_removed_with_what_it_holds(self):
        dialog = ManageFavouritesDialog(_favourites())
        _tree_item(dialog, 1).setSelected(True)
        _tree_item(dialog, 0).setSelected(True)

        dialog.remove_selected()

        assert [i.name for i in dialog.favourites().root] == ["Empty"]

    @pytest.mark.parametrize(
        ("picked", "made_in"),
        [(None, ()), ((1,), (1,)), ((1, 0), (1,))],
    )
    def test_a_folder_made_where_picked(self, monkeypatch, picked, made_in):
        dialog = ManageFavouritesDialog(_favourites())
        if picked is not None:
            dialog.tree.setCurrentItem(_tree_item(dialog, *picked))
        _typed(monkeypatch, "Made")

        dialog.new_folder()

        items = dialog.favourites().items_at(made_in)
        assert items[-1] == FavouriteFolder(name="Made")

    def test_rename_and_remove_with_something_picked(self):
        dialog = ManageFavouritesDialog(_favourites())

        assert not dialog.remove_button.isEnabled()

        _tree_item(dialog, 0).setSelected(True)
        assert dialog.rename_button.isEnabled()

        _tree_item(dialog, 1).setSelected(True)
        assert not dialog.rename_button.isEnabled()
        assert dialog.remove_button.isEnabled()
