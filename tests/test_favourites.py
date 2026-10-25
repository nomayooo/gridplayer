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
from PyQt5.QtWidgets import QMessageBox, QWidget

from gridplayer.dialogs import favourites as dialogs
from gridplayer.dialogs.favourites import (
    AddAllFavouritesDialog,
    AddFavouriteDialog,
    ImportPlaylistsDialog,
    ManageFavouritesDialog,
)
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
# a file none of the favourites are of
NEW = HERE.parent / "conftest.py"
GONE = HERE.parent / "no such video.mp4"


def _video(name="Clip", path=HERE, loops=(), loop_start=None, position=None):
    return FavouriteVideo(
        name=name,
        path=path,
        loops=list(loops),
        loop_start=loop_start,
        position=position,
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
        assert read.root[0].position is None
        assert (read.root[0].loop_index, read.root[0].is_outside_loops) == (0, False)

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

    def test_the_favourite_of_a_file_is_found(self):
        folder, video = _favourites().find_video(HERE)

        assert (folder, video.name) == ((), "Top")
        assert _favourites().find_video(NEW) is None

    def test_one_of_a_file_kept_under_the_name_is_replaced_where_it_is(self):
        favourites = Favourites(
            [_video("A", path=NEW), _video("Same"), _video("B", path=NEW.parent)]
        )

        favourites.put_video((), _video("Same", loops=[(1, 2)]))

        assert [i.name for i in favourites.root] == ["A", "Same", "B"]
        assert favourites.root[1].loops == [(1, 2)]

    def test_one_kept_under_the_name_in_another_folder_is_moved(self):
        favourites = _favourites()

        favourites.put_video((1, 1), _video("Top"))

        assert [i.name for i in favourites.root] == ["Music", "Empty"]
        assert [i.name for i in favourites.items_at((0, 1))] == ["Gig", "Top"]

    def test_under_another_name_one_more(self):
        favourites = Favourites([_video("A")])

        favourites.put_video((), _video("A (2)", position=5000))

        assert [(i.name, i.position) for i in favourites.root] == [
            ("A", None),
            ("A (2)", 5000),
        ]

    def test_the_same_name_of_another_file_is_another(self):
        favourites = Favourites([_video("A")])

        favourites.put_video((), _video("A", path=NEW))

        assert [i.path for i in favourites.root] == [HERE, NEW]

    def test_several_into_a_folder_below_ones_they_take_the_place_of(self):
        # the folder after the two it takes in: each taken out moves it up
        favourites = Favourites(
            [_video("a"), _video("b", path=NEW), FavouriteFolder(name="New")]
        )

        favourites.put_videos((2,), [_video("a"), _video("b", path=NEW)])

        assert [i.name for i in favourites.root] == ["New"]
        assert [i.name for i in favourites.items_at((0,))] == ["a", "b"]

    def test_into_a_folder_only_those_elsewhere_left(self):
        favourites = Favourites([_video("a"), FavouriteFolder(name="New")])

        favourites.put_videos((1,), [_video("a")], is_folder_only=True)

        assert [i.name for i in favourites.root] == ["a", "New"]
        assert [i.name for i in favourites.items_at((1,))] == ["a"]

    def test_the_names_a_file_is_kept_under(self):
        assert _favourites().names_of(HERE) == {"Top", "Song", "Gig"}
        assert _favourites().names_of(NEW) == set()

    def test_a_file_not_kept_is_added_at_the_end(self):
        favourites = _favourites()

        favourites.put_video((2,), _video("New", path=NEW))

        assert [i.name for i in favourites.items_at((2,))] == ["New"]

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


def _manager(active=None, selected=()):
    commands = MagicMock()
    commands.selected_cells = lambda: list(selected)
    ctx = SimpleNamespace(active_block=active, commands=commands)

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

    def test_a_folder_of_empty_folders_alone_has_no_open_all(self, stored):
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


class TestOpeningInNewWindows:
    @pytest.fixture
    def nested(self, stored, tmp_path):
        files = {}
        for name in ("own", "a", "b", "c"):
            files[name] = tmp_path / f"{name}.mp4"
            files[name].write_bytes(b"video")

        def fav(name, **fields):
            return FavouriteVideo(name=name, path=files[name], **fields)

        stored["favourites"] = Favourites(
            [
                FavouriteFolder(
                    name="Playlists",
                    items=[
                        fav("own"),
                        FavouriteFolder(name="One", items=[fav("a", position=5000)]),
                        FavouriteFolder(
                            name="Two",
                            items=[
                                fav("b"),
                                FavouriteFolder(name="Deep", items=[fav("c")]),
                            ],
                        ),
                    ],
                )
            ]
        )
        return files

    def test_its_own_here_each_folder_in_a_window_of_its_own(self, nested):
        manager = _manager()

        manager.cmd_open_favourites_folder((0,))

        commands = manager._ctx.commands
        ((here,), _) = commands.add_favourite_videos.call_args
        assert [v.name for v in here] == ["own"]

        windows = [c.args[0] for c in commands.open_in_new_window.call_args_list]
        assert [[v.uri for v in w] for w in windows] == [
            [nested["a"]],
            [nested["b"]],
            [nested["c"]],
        ]
        # each where it was kept
        assert windows[0][0].current_position == 5000

    def test_into_an_empty_window_the_first_folder_here(self, nested, stored):
        stored["favourites"].root[0].items.pop(0)
        manager = _manager()
        manager._ctx.commands.is_videos = lambda: False

        manager.cmd_open_favourites_folder((0,))

        commands = manager._ctx.commands
        ((here,), _) = commands.add_favourite_videos.call_args
        assert [v.name for v in here] == ["a"]
        windows = [c.args[0] for c in commands.open_in_new_window.call_args_list]
        assert [[v.uri for v in w] for w in windows] == [[nested["b"]], [nested["c"]]]

    def test_with_videos_open_here_every_folder_apart(self, nested, stored):
        stored["favourites"].root[0].items.pop(0)
        manager = _manager()
        manager._ctx.commands.is_videos = lambda: True

        manager.cmd_open_favourites_folder((0,))

        manager._ctx.commands.add_favourite_videos.assert_not_called()
        assert manager._ctx.commands.open_in_new_window.call_count == 3

    def test_with_its_own_videos_the_folders_apart_window_empty_or_not(self, nested):
        manager = _manager()
        manager._ctx.commands.is_videos = lambda: False

        manager.cmd_open_favourites_folder((0,))

        ((here,), _) = manager._ctx.commands.add_favourite_videos.call_args
        assert [v.name for v in here] == ["own"]
        assert manager._ctx.commands.open_in_new_window.call_count == 3

    def test_a_folder_of_its_own_videos_alone_opens_here_only(self, nested):
        manager = _manager()

        manager.cmd_open_favourites_folder((0, 1))

        manager._ctx.commands.add_favourite_videos.assert_called_once()
        manager._ctx.commands.open_in_new_window.assert_not_called()

    def test_files_gone_said_the_rest_opened(self, nested):
        nested["b"].unlink()
        manager = _manager()
        errors = []
        manager.error.connect(errors.append)

        manager.cmd_open_favourites_folder((0,))

        windows = [
            c.args[0] for c in manager._ctx.commands.open_in_new_window.call_args_list
        ]
        # Two had only b, gone: no window for it
        assert [[v.uri for v in w] for w in windows] == [
            [nested["a"]],
            [nested["c"]],
        ]
        assert len(errors) == 1
        assert str(nested["b"]) in errors[0]

    def test_open_all_offered_for_a_folder_of_folders(self, nested, stored):
        stored["favourites"].root[0].items.pop(0)

        menu = _manager().menu_generator_favourites_folder((0,))

        assert menu[-1]["func"] == ("open_favourites_folder", (0,))


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

    def test_at_where_it_was_kept_at(self, adder):
        adder.add_favourite_videos(
            [
                _video(
                    loops=[(1000, 2000), (5000, 6000)],
                    loop_start=9000,
                    position=5500,
                ),
                FavouriteVideo(
                    name="Outside",
                    path=HERE,
                    loops=[(1000, 2000), (5000, 6000)],
                    position=3000,
                    loop_index=1,
                    is_outside_loops=True,
                ),
            ]
        )

        ((begun, outside),) = adder.added
        assert begun.current_position == 5500
        assert (outside.current_position, outside.loop_index) == (3000, 1)
        assert outside.is_outside_loops

    def test_one_kept_before_positions_were_opens_as_before(self, adder):
        adder.add_favourite_videos([_video()])

        ((video,),) = adder.added
        assert video.current_position == 0

    def test_a_file_gone_is_said_and_the_rest_opened(self, adder):
        adder.add_favourite_videos([_video(path=GONE), _video()])

        assert [len(batch) for batch in adder.added] == [1]
        (error,) = adder.errors
        assert str(GONE) in error

    def test_nothing_opened_when_none_are_there(self, adder):
        adder.add_favourite_videos([_video(path=GONE)])

        assert adder.added == []
        adder._ctx.commands.add_recent_uris.assert_not_called()


def _block(
    uri=NEW,
    title="Shown title",
    loops=(),
    loop_start=None,
    position=0,
    loop_index=0,
    is_outside_loops=False,
):
    return SimpleNamespace(
        is_local_file=isinstance(uri, Path),
        title=title,
        video_params=SimpleNamespace(
            uri=uri,
            loops=list(loops),
            loop_start=loop_start,
            current_position=position,
            loop_index=loop_index,
            is_outside_loops=is_outside_loops,
        ),
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
        assert added == FavouriteVideo(
            name="My clip", path=NEW, loops=[(500, 900)], position=0
        )

    def test_a_loop_begun_and_not_finished_kept_too(self, stored, monkeypatch):
        asked = Mock(return_value=(stored["favourites"], (), "Begun"))
        monkeypatch.setattr(manager_module.AddFavouriteDialog, "ask", asked)

        _manager(active=_block(loop_start=12_000)).cmd_add_to_favourites()

        assert asked.call_args.kwargs["loops"] == 0
        assert asked.call_args.kwargs["loop_start"] == 12_000
        added = stored["favourites"].root[-1]
        assert (added.loops, added.loop_start) == ([], 12_000)

    def test_where_it_is_kept_with_it(self, stored, monkeypatch):
        asked = Mock(return_value=(stored["favourites"], (), "Here"))
        monkeypatch.setattr(manager_module.AddFavouriteDialog, "ask", asked)
        block = _block(
            loops=[(1, 2), (5, 9)], position=83_456, loop_index=1, is_outside_loops=True
        )

        _manager(active=block).cmd_add_to_favourites()

        assert asked.call_args.kwargs["position"] == 83_456
        added = stored["favourites"].root[-1]
        assert (added.position, added.loop_index, added.is_outside_loops) == (
            83_456,
            1,
            True,
        )

    def test_named_after_the_file_without_a_title(self, stored, monkeypatch):
        asked = Mock(return_value=None)
        monkeypatch.setattr(manager_module.AddFavouriteDialog, "ask", asked)

        _manager(active=_block(title=None)).cmd_add_to_favourites()

        assert asked.call_args.kwargs["name"] == NEW.stem

    def test_one_already_kept_is_offered_as_it_is(self, stored, monkeypatch):
        asked = Mock(return_value=None)
        monkeypatch.setattr(manager_module.AddFavouriteDialog, "ask", asked)
        stored["favourites"] = Favourites(
            [FavouriteFolder(name="Music", items=[_video("Song", path=NEW)])]
        )

        _manager(active=_block()).cmd_add_to_favourites()

        kwargs = asked.call_args.kwargs
        assert (kwargs["name"], kwargs["folder"], kwargs["kept_names"]) == (
            "Song",
            (0,),
            {"Song"},
        )

    def test_a_new_one_is_offered_at_the_top(self, stored, monkeypatch):
        asked = Mock(return_value=None)
        monkeypatch.setattr(manager_module.AddFavouriteDialog, "ask", asked)

        _manager(active=_block()).cmd_add_to_favourites()

        assert (
            asked.call_args.kwargs["folder"],
            asked.call_args.kwargs["kept_names"],
        ) == (
            (),
            set(),
        )

    def test_one_already_kept_is_replaced(self, stored, monkeypatch):
        stored["favourites"] = Favourites(
            [
                _video("Before"),
                FavouriteFolder(name="Music", items=[_video("Old", path=NEW)]),
            ]
        )
        monkeypatch.setattr(
            manager_module.AddFavouriteDialog,
            "ask",
            Mock(return_value=(stored["favourites"], (1,), "Old")),
        )

        _manager(active=_block(loops=[(1, 2)])).cmd_add_to_favourites()

        assert stored["favourites"].items_at((1,)) == [
            FavouriteVideo(name="Old", path=NEW, loops=[(1, 2)], position=0)
        ]

    def test_renamed_it_is_one_more(self, stored, monkeypatch):
        stored["favourites"] = Favourites([_video("Old", path=NEW)])
        monkeypatch.setattr(
            manager_module.AddFavouriteDialog,
            "ask",
            Mock(return_value=(stored["favourites"], (), "Intro")),
        )

        _manager(active=_block()).cmd_add_to_favourites()

        assert [i.name for i in stored["favourites"].root] == ["Old", "Intro"]

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

    def test_opened_from_the_manager_into_the_grid(self, stored, monkeypatch):
        def edit(parent, favourites, on_open):
            on_open([favourites.root[0]], [])
            return None

        monkeypatch.setattr(manager_module.ManageFavouritesDialog, "edit", edit)
        manager = _manager()

        manager.cmd_manage_favourites()

        manager._ctx.commands.add_favourite_videos.assert_called_once_with(
            [stored["favourites"].root[0]]
        )
        manager._ctx.commands.open_in_new_window.assert_not_called()

    def test_put_in_order_not_kept_on_cancel(self, stored, monkeypatch):
        before = stored["favourites"]
        monkeypatch.setattr(
            manager_module.ManageFavouritesDialog, "edit", Mock(return_value=None)
        )

        _manager().cmd_manage_favourites()

        assert stored["favourites"] is before


def _answered(monkeypatch, answer):
    """Each "are you sure?" answered so, and what it asked kept."""

    asked = []

    def question(_parent, _title, text, **_kwargs):
        asked.append(text)
        return answer

    monkeypatch.setattr(dialogs.QCustomMessageBox, "question", question)

    return asked


def _typed(monkeypatch, text):
    monkeypatch.setattr(
        dialogs.QCustomTextInput, "get_text", lambda *_args, **_kwargs: text
    )


def _grid_of(*blocks):
    """A manager whose grid has these cells, in this order."""

    for index, block in enumerate(blocks):
        block.video_params.id = str(index)

    manager = _manager()
    manager._ctx.commands.layout_order = lambda: [str(i) for i in range(len(blocks))]
    manager._ctx.video_blocks = SimpleNamespace(
        blocks_for_ids=lambda ids: [blocks[int(i)] for i in ids]
    )

    return manager


class TestMakingAll:
    def test_each_under_its_own_name_with_its_loops(self, stored, monkeypatch):
        stored["favourites"] = Favourites([FavouriteFolder(name="Grid")])
        asked = Mock(return_value=(stored["favourites"], (0,)))
        monkeypatch.setattr(manager_module.AddAllFavouritesDialog, "ask", asked)
        first = _block(uri=NEW, title="First", loops=[(1, 2)])
        second = _block(uri=HERE, title=None, loop_start=500)

        _grid_of(first, second).cmd_add_all_to_favourites()

        assert stored["favourites"].items_at((0,)) == [
            FavouriteVideo(name="First", path=NEW, loops=[(1, 2)], position=0),
            FavouriteVideo(name=HERE.stem, path=HERE, loop_start=500, position=0),
        ]
        assert (
            asked.call_args.kwargs["count"],
            asked.call_args.kwargs["left_out"],
        ) == (
            2,
            0,
        )

    def test_streams_left_out_and_said_to_be(self, stored, monkeypatch):
        asked = Mock(return_value=(stored["favourites"], (2,)))
        monkeypatch.setattr(manager_module.AddAllFavouritesDialog, "ask", asked)

        _grid_of(
            _block(uri="https://example.com/v"), _block(uri=NEW)
        ).cmd_add_all_to_favourites()

        assert (
            asked.call_args.kwargs["count"],
            asked.call_args.kwargs["left_out"],
        ) == (
            1,
            1,
        )
        assert [v.path for v in stored["favourites"].items_at((2,))] == [NEW]

    def test_ones_already_kept_replaced(self, stored, monkeypatch):
        # HERE is a favourite as "Song" in Music, and elsewhere as others
        monkeypatch.setattr(
            manager_module.AddAllFavouritesDialog,
            "ask",
            Mock(return_value=(stored["favourites"], (1,))),
        )

        _grid_of(_block(uri=HERE, title="Song", position=7)).cmd_add_all_to_favourites()

        favourites = stored["favourites"]
        songs = [i for i in favourites.items_at((1,)) if i.name == "Song"]
        assert [s.position for s in songs] == [7]
        assert favourites.names_of(HERE) == {"Top", "Song", "Gig"}

    def test_copies_of_one_file_each_kept_numbered(self, stored, monkeypatch):
        stored["favourites"] = Favourites()
        monkeypatch.setattr(
            manager_module.AddAllFavouritesDialog,
            "ask",
            Mock(return_value=(stored["favourites"], ())),
        )
        grid = [
            _block(title="A", position=30_000),
            _block(uri=HERE, title="Other"),
            _block(title="A", position=105_000),
            _block(title="A", position=180_000),
        ]

        _grid_of(*grid).cmd_add_all_to_favourites()

        assert [(i.name, i.position) for i in stored["favourites"].root] == [
            ("A", 30_000),
            ("Other", 0),
            ("A (2)", 105_000),
            ("A (3)", 180_000),
        ]

    def test_into_a_folder_made_below_them(self, stored, monkeypatch):
        # already favourites at the top, the folder made in the window after
        def ask(**kwargs):
            favourites = kwargs["favourites"]
            favourites.root.append(FavouriteFolder(name="Made"))
            return favourites, (len(favourites.root) - 1,)

        stored["favourites"] = Favourites(
            [_video("A", path=NEW), _video("A (2)", path=NEW)]
        )
        monkeypatch.setattr(manager_module.AddAllFavouritesDialog, "ask", ask)

        _grid_of(_block(title="A"), _block(title="A")).cmd_add_all_to_favourites()

        favourites = stored["favourites"]
        assert [i.name for i in favourites.root] == ["Made"]
        assert [i.name for i in favourites.items_at((0,))] == ["A", "A (2)"]

    def test_copies_added_again_replace_their_own(self, stored, monkeypatch):
        stored["favourites"] = Favourites()
        monkeypatch.setattr(
            manager_module.AddAllFavouritesDialog,
            "ask",
            Mock(return_value=(stored["favourites"], ())),
        )
        _grid_of(_block(title="A"), _block(title="A")).cmd_add_all_to_favourites()

        _grid_of(
            _block(title="A", position=1), _block(title="A", position=2)
        ).cmd_add_all_to_favourites()

        assert [(i.name, i.position) for i in stored["favourites"].root] == [
            ("A", 1),
            ("A (2)", 2),
        ]

    def test_nothing_kept_when_thought_better_of(self, stored, monkeypatch):
        before = stored["favourites"].model_copy(deep=True)
        monkeypatch.setattr(
            manager_module.AddAllFavouritesDialog, "ask", Mock(return_value=None)
        )

        _grid_of(_block(uri=NEW)).cmd_add_all_to_favourites()

        assert stored["favourites"] == before

    def test_not_asked_with_no_file_open(self, stored, monkeypatch):
        asked = Mock()
        monkeypatch.setattr(manager_module.AddAllFavouritesDialog, "ask", asked)

        _grid_of(_block(uri="https://example.com/v")).cmd_add_all_to_favourites()

        asked.assert_not_called()


class TestMakingTheSelected:
    def test_all_at_once_into_the_folder_picked(self, stored, monkeypatch):
        asked = Mock(return_value=(stored["favourites"], (2,)))
        monkeypatch.setattr(manager_module.AddAllFavouritesDialog, "ask", asked)
        single = Mock()
        monkeypatch.setattr(manager_module.AddFavouriteDialog, "ask", single)
        picked = [_block(title="One"), _block(uri=Path("two.mp4"), title="Two")]

        _manager(active=_block(title="Active"), selected=picked).cmd_add_to_favourites()

        single.assert_not_called()
        assert asked.call_args.kwargs["count"] == 2
        assert asked.call_args.kwargs["is_selected"] is True
        names = [v.name for v in stored["favourites"].items_at((2,))]
        assert names == ["One", "Two"]

    def test_streams_among_them_left_out(self, stored, monkeypatch):
        asked = Mock(return_value=None)
        monkeypatch.setattr(manager_module.AddAllFavouritesDialog, "ask", asked)
        stream = _block(title="Stream")
        stream.is_local_file = False

        _manager(selected=[_block(), stream]).cmd_add_to_favourites()

        assert asked.call_args.kwargs["count"] == 1
        assert asked.call_args.kwargs["left_out"] == 1

    def test_whether_there_is_any(self):
        stream = _block()
        stream.is_local_file = False

        assert _manager(active=_block()).is_any_to_favourite()
        assert not _manager(active=None).is_any_to_favourite()
        assert not _manager(active=_block(), selected=[stream]).is_any_to_favourite()
        assert _manager(active=stream, selected=[_block()]).is_any_to_favourite()


def _playlist(path, *videos):
    from gridplayer.models.playlist import Playlist

    Playlist(videos=list(videos), save_position=True).save(path)
    return path


@pytest.fixture
def importing(stored, monkeypatch):
    """Playlists picked, the window answered (by default: into the top,
    under their own names); what was asked, and what was said."""

    state = SimpleNamespace(
        picked=[],
        answer=lambda favourites, names: (favourites, (), names),
        asked=[],
    )

    monkeypatch.setattr(
        manager_module.QFileDialog,
        "getOpenFileNames",
        lambda *_a, **_k: ([str(p) for p in state.picked], ""),
    )

    def ask(parent, favourites, names):
        state.asked.append(names)
        return state.answer(favourites, names)

    monkeypatch.setattr(manager_module.ImportPlaylistsDialog, "ask", ask)

    manager = _manager()
    state.errors = []
    manager.error.connect(state.errors.append)
    state.manager = manager
    stored["favourites"] = Favourites([_video("Kept")])

    return state


class TestImportingPlaylists:
    def test_one_into_a_folder_of_its_name(self, importing, stored, tmp_path):
        from gridplayer.models.video import Video

        importing.picked = [
            _playlist(
                tmp_path / "Mix.gpls",
                Video(uri=HERE, loops=[(1000, 2000)], current_position=1500),
                Video(uri=NEW, title="Titled"),
            )
        ]

        importing.manager.cmd_import_playlists()

        assert importing.asked == [["Mix"]]
        root = stored["favourites"].root
        assert [i.name for i in root] == ["Kept", "Mix"]
        videos = root[1].items
        assert [(v.name, v.path) for v in videos] == [
            (HERE.name, HERE),
            ("Titled", NEW),
        ]
        assert (videos[0].loops, videos[0].position) == ([(1000, 2000)], 1500)

    def test_one_saved_without_positions_opens_as_a_new_one(
        self, importing, stored, tmp_path
    ):
        from gridplayer.models.playlist import Playlist
        from gridplayer.models.video import Video

        path = tmp_path / "Mix.gpls"
        Playlist(
            videos=[Video(uri=HERE, current_position=1500)], save_position=False
        ).save(path)
        importing.picked = [path]

        importing.manager.cmd_import_playlists()

        assert stored["favourites"].root[1].items[0].position is None

    def test_into_the_folder_picked_or_made(self, importing, stored, tmp_path):
        from gridplayer.models.video import Video

        def into_made(favourites, names):
            favourites.root.append(FavouriteFolder(name="Playlists"))
            return favourites, (1,), names

        importing.answer = into_made
        importing.picked = [
            _playlist(tmp_path / "One.gpls", Video(uri=HERE)),
            _playlist(tmp_path / "Two.gpls", Video(uri=NEW)),
        ]

        importing.manager.cmd_import_playlists()

        root = stored["favourites"].root
        assert [i.name for i in root] == ["Kept", "Playlists"]
        assert [i.name for i in root[1].items] == ["One", "Two"]
        assert [v.path for v in root[1].items[1].items] == [NEW]

    def test_again_into_the_same_folder_picked(self, importing, stored, tmp_path):
        from gridplayer.models.video import Video

        stored["favourites"] = Favourites(
            [
                FavouriteFolder(
                    name="Playlists",
                    items=[FavouriteFolder(name="Mix", items=[_video("Old")])],
                )
            ]
        )
        importing.answer = lambda favourites, names: (favourites, (0,), names)
        importing.picked = [_playlist(tmp_path / "Mix.gpls", Video(uri=NEW))]

        importing.manager.cmd_import_playlists()

        mix = stored["favourites"].root[0].items
        assert [i.name for i in mix] == ["Mix"]
        assert [v.name for v in mix[0].items] == ["Old", NEW.name]

    def test_one_renamed(self, importing, stored, tmp_path):
        from gridplayer.models.video import Video

        importing.picked = [_playlist(tmp_path / "Mix.gpls", Video(uri=HERE))]
        importing.answer = lambda favourites, _names: (favourites, (), ["Evening"])

        importing.manager.cmd_import_playlists()

        assert [i.name for i in stored["favourites"].root] == ["Kept", "Evening"]

    def test_one_not_imported_when_thought_better_of(self, importing, stored, tmp_path):
        from gridplayer.models.video import Video

        before = stored["favourites"].model_copy(deep=True)
        importing.picked = [_playlist(tmp_path / "Mix.gpls", Video(uri=HERE))]
        importing.answer = lambda _favourites, _names: None

        importing.manager.cmd_import_playlists()

        assert stored["favourites"] == before

    def test_several_under_their_own_names_unasked(self, importing, stored, tmp_path):
        from gridplayer.models.video import Video

        importing.picked = [
            _playlist(tmp_path / "One.gpls", Video(uri=HERE)),
            _playlist(tmp_path / "Two.gpls", Video(uri=NEW)),
        ]

        importing.manager.cmd_import_playlists()

        assert importing.asked == [["One", "Two"]]
        root = stored["favourites"].root
        assert [i.name for i in root] == ["Kept", "One", "Two"]
        assert [v.path for v in root[2].items] == [NEW]

    def test_copies_numbered_and_streams_left_out(self, importing, stored, tmp_path):
        from gridplayer.models.video import Video

        importing.picked = [
            _playlist(
                tmp_path / "Mix.gpls",
                Video(uri=HERE, current_position=1),
                Video(uri="https://example.com/live.m3u8"),
                Video(uri=HERE, current_position=2),
            )
        ]

        importing.manager.cmd_import_playlists()

        videos = stored["favourites"].root[1].items
        assert [(v.name, v.position) for v in videos] == [
            (HERE.name, 1),
            (f"{HERE.name} (2)", 2),
        ]

    def test_a_video_in_two_kept_in_both(self, importing, stored, tmp_path):
        from gridplayer.models.video import Video

        importing.picked = [
            _playlist(tmp_path / "One.gpls", Video(uri=HERE), Video(uri=NEW)),
            _playlist(tmp_path / "Two.gpls", Video(uri=NEW)),
        ]

        importing.manager.cmd_import_playlists()

        root = stored["favourites"].root
        assert [v.path for v in root[1].items] == [HERE, NEW]
        assert [v.path for v in root[2].items] == [NEW]

    def test_imported_again_into_the_same_folder(self, importing, stored, tmp_path):
        from gridplayer.models.video import Video

        path = tmp_path / "Mix.gpls"
        importing.picked = [_playlist(path, Video(uri=HERE, current_position=1))]
        importing.manager.cmd_import_playlists()

        _playlist(path, Video(uri=HERE, current_position=2))
        importing.manager.cmd_import_playlists()

        root = stored["favourites"].root
        assert [i.name for i in root] == ["Kept", "Mix"]
        assert [v.position for v in root[1].items] == [2]

    def test_ones_that_could_not_be_read_or_have_no_files_said(
        self, importing, stored, tmp_path
    ):
        from gridplayer.models.video import Video

        broken = tmp_path / "Broken.gpls"
        broken.write_text("{ not a playlist")
        importing.picked = [
            broken,
            _playlist(tmp_path / "Streams.gpls", Video(uri="https://example.com/a")),
            _playlist(tmp_path / "Good.gpls", Video(uri=HERE)),
        ]

        importing.manager.cmd_import_playlists()

        assert [i.name for i in stored["favourites"].root] == ["Kept", "Good"]
        assert importing.errors == [
            "Couldn't read Broken.gpls\nNo video files in Streams.gpls"
        ]

    def test_nothing_when_none_picked(self, importing, stored):
        before = stored["favourites"].model_copy(deep=True)

        importing.manager.cmd_import_playlists()

        assert stored["favourites"] == before
        assert importing.asked == []


class TestTheImportWindow:
    def test_one_named_as_it_is_or_renamed(self):
        dialog = ImportPlaylistsDialog(_favourites(), names=["Mix"])

        assert dialog.windowTitle() == "Import Playlist"
        assert dialog.names == ["Mix"]
        dialog.name.setText(" Evening ")
        assert dialog.names == ["Evening"]

        dialog.name.setText(" ")
        assert not dialog.ok_button.isEnabled()

    def test_several_under_their_own_names_counted(self):
        dialog = ImportPlaylistsDialog(_favourites(), names=["One", "Two"])

        assert dialog.windowTitle() == "Import Playlists"
        assert dialog.name is None
        assert dialog.names == ["One", "Two"]
        assert "2" in dialog.count_note.text()

    def test_into_the_top_unless_another_is_picked(self, monkeypatch):
        dialog = ImportPlaylistsDialog(_favourites(), names=["Mix"])
        assert dialog.selected_folder == ()

        _typed(monkeypatch, "Playlists")
        dialog.new_folder()

        assert dialog.selected_folder == (3,)
        assert dialog.favourites.root[3].name == "Playlists"


class TestSavingASession:
    def test_the_files_open_here_as_they_are_in_the_grids_order(self, stored):
        manager = _grid_of(
            _block(title="One", position=1000, loops=[(0, 500)]),
            _block(uri="https://example.com/live", title="Stream"),
            _block(uri=HERE, title="Two", position=2000),
        )

        videos = manager.session_favourites()

        assert [(v.name, v.position, v.loops) for v in videos] == [
            ("One", 1000, [(0, 500)]),
            ("Two", 2000, []),
        ]

    def test_each_window_in_a_numbered_folder_of_the_session(self, stored):
        windows = [
            [_video("a", path=NEW), _video("a", path=NEW, position=5)],
            [_video("b")],
        ]

        _manager().save_session_favourites("2026-10-25 14:03:27", windows)

        root = stored["favourites"].root
        session = root[-1]
        assert session.name == "2026-10-25 14:03:27"
        assert [f.name for f in session.items] == ["1", "2"]
        assert [v.name for v in session.items[0].items] == ["a", "a (2)"]
        assert [v.name for v in session.items[1].items] == ["b"]
        # what was there before kept as it was
        assert [i.name for i in root[:-1]] == ["Top", "Music", "Empty"]


@pytest.fixture
def session(monkeypatch, tmp_path):
    """The session manager, the others' answers and what was said set."""

    from gridplayer.player.managers import session as session_module

    state = SimpleNamespace(others=[], said=[])
    monkeypatch.setattr(session_module, "get_app_data_dir", lambda: tmp_path)
    monkeypatch.setattr(
        session_module, "ask_other_windows", lambda *_a, **_k: state.others
    )
    monkeypatch.setattr(
        session_module.QCustomMessageBox,
        "information",
        lambda _parent, _title, text, **kwargs: state.said.append(
            (text, kwargs.get("info", ""))
        ),
    )

    commands = MagicMock()
    manager = session_module.SessionManager(context=SimpleNamespace(commands=commands))
    manager.init()
    state.manager = manager
    state.commands = commands
    yield state
    manager.cleanup()


class TestTheSessionManager:
    def test_this_window_first_then_the_others(self, session):
        session.commands.session_favourites.return_value = [_video("mine")]
        session.others = [
            [_video("first").model_dump(mode="json")],
            [],
            [_video("third").model_dump(mode="json")],
        ]

        session.manager.cmd_save_session()

        ((name, windows), _) = session.commands.save_session_favourites.call_args
        assert [[v.name for v in w] for w in windows] == [
            ["mine"],
            ["first"],
            ["third"],
        ]
        assert len(name) == len("2026-10-25 14:03:27")
        ((text, info),) = session.said
        assert name in text
        assert info == "Windows: 3, videos: 3"

    def test_none_open_anywhere_nothing_saved(self, session):
        session.commands.session_favourites.return_value = []

        session.manager.cmd_save_session()

        session.commands.save_session_favourites.assert_not_called()
        assert session.said == [("No video files are open to save.", "")]

    def test_a_window_saying_nonsense_left_out(self, session):
        session.commands.session_favourites.return_value = [_video("mine")]
        session.others = [[{"not": "a favourite"}]]

        session.manager.cmd_save_session()

        ((_, windows), _) = session.commands.save_session_favourites.call_args
        assert len(windows) == 1

    def test_this_window_known_to_the_others_while_open(self, session, tmp_path):
        files = list((tmp_path / "windows").glob("*.json"))
        assert [f.stem for f in files] == [session.manager._server.id]

        session.manager.cleanup()

        assert not list((tmp_path / "windows").glob("*.json"))


class TestTheAddAllWindow:
    def test_titled_for_the_selected(self):
        all_of_them = AddAllFavouritesDialog(Favourites(), count=2, left_out=0)
        selected = AddAllFavouritesDialog(
            Favourites(), count=2, left_out=0, is_selected=True
        )

        assert all_of_them.windowTitle() == "Add All to Favourites"
        assert selected.windowTitle() == "Add Selected to Favourites"

    def test_a_folder_picked_or_made(self, monkeypatch):
        dialog = AddAllFavouritesDialog(_favourites(), count=3, left_out=0)
        _typed(monkeypatch, "This grid")

        dialog.new_folder()

        assert dialog.selected_folder == (3,)
        assert dialog.favourites.root[3] == FavouriteFolder(name="This grid")

    def test_how_many_said(self):
        dialog = AddAllFavouritesDialog(Favourites(), count=3, left_out=2)

        assert "3" in dialog.count_note.text()
        assert not dialog.left_out_note.isHidden()
        assert "2" in dialog.left_out_note.text()

    def test_none_left_out_not_said(self):
        dialog = AddAllFavouritesDialog(Favourites(), count=3, left_out=0)

        assert dialog.left_out_note.isHidden()


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

    def test_one_already_kept_opens_where_it_is_and_says_so(self):
        dialog = AddFavouriteDialog(
            _favourites(),
            name="Gig",
            loops=0,
            folder=(1, 1),
            kept_names=frozenset({"Gig", "Song"}),
        )

        assert dialog.selected_folder == (1, 1)
        assert not dialog.kept_note.isHidden()
        assert AddFavouriteDialog(_favourites(), name="C", loops=0).kept_note.isHidden()

    def test_renamed_it_no_longer_says_so(self):
        dialog = AddFavouriteDialog(
            _favourites(), name="Gig", loops=0, kept_names=frozenset({"Gig", "Song"})
        )

        dialog.name.setText("Intro")
        assert dialog.kept_note.isHidden()

        dialog.name.setText(" Song ")
        assert not dialog.kept_note.isHidden()

    def test_the_loops_kept_are_said(self):
        assert AddFavouriteDialog(Favourites(), name="C", loops=0).loops_note.isHidden()

        dialog = AddFavouriteDialog(Favourites(), name="C", loops=3)
        assert not dialog.loops_note.isHidden()
        assert "3" in dialog.loops_note.text()
        assert dialog.loop_start_note.isHidden()

    def test_where_it_opens_is_said(self):
        dialog = AddFavouriteDialog(Favourites(), name="C", loops=0, position=83_456)

        assert not dialog.position_note.isHidden()
        assert "1:23.456" in dialog.position_note.text()
        assert AddFavouriteDialog(
            Favourites(), name="C", loops=0
        ).position_note.isHidden()

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

    def test_where_each_opens_is_shown(self):
        favourites = Favourites([_video("At"), _video("Never")])
        favourites.root[0].position = 83_456

        dialog = ManageFavouritesDialog(favourites)

        assert _tree_item(dialog, 0).text(2) == "1:23.456"
        assert _tree_item(dialog, 1).text(2) == ""
        assert _tree_item(dialog, 0).text(3) == str(HERE)
        assert dialog.favourites() == favourites

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

    def test_removed_with_what_it_holds(self, monkeypatch):
        asked = _answered(monkeypatch, QMessageBox.Yes)
        dialog = ManageFavouritesDialog(_favourites())
        _tree_item(dialog, 1).setSelected(True)
        _tree_item(dialog, 0).setSelected(True)

        dialog.remove_selected()

        assert [i.name for i in dialog.favourites().root] == ["Empty"]
        assert asked == ['Remove the folder "Music" and everything in it?']

    def test_a_folder_kept_when_not_sure(self, monkeypatch):
        _answered(monkeypatch, QMessageBox.No)
        dialog = ManageFavouritesDialog(_favourites())
        _tree_item(dialog, 1).setSelected(True)
        _tree_item(dialog, 0).setSelected(True)

        dialog.remove_selected()

        assert dialog.favourites() == _favourites()

    def test_folders_asked_about_together(self, monkeypatch):
        asked = _answered(monkeypatch, QMessageBox.Yes)
        dialog = ManageFavouritesDialog(_favourites())
        _tree_item(dialog, 1).setSelected(True)
        _tree_item(dialog, 2).setSelected(True)

        dialog.remove_selected()

        assert [i.name for i in dialog.favourites().root] == ["Top"]
        assert asked == ["Remove 2 folders and everything in them?"]

    def test_videos_alone_removed_without_asking(self, monkeypatch):
        asked = _answered(monkeypatch, QMessageBox.No)
        dialog = ManageFavouritesDialog(_favourites())
        _tree_item(dialog, 0).setSelected(True)
        _tree_item(dialog, 1, 0).setSelected(True)

        dialog.remove_selected()

        favourites = dialog.favourites()
        assert [i.name for i in favourites.root] == ["Music", "Empty"]
        assert len(favourites.items_at((0,))) == 1
        assert asked == []

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

    def _opened(self, dialog):
        """What each open asked for: the names here, and those of each new
        window."""

        opened = []
        dialog.open_requested.connect(
            lambda here, apart: opened.append(
                ([v.name for v in here], [[v.name for v in w] for w in apart])
            )
        )
        return opened

    def test_a_folder_opened_its_own_here_its_folders_apart(self):
        dialog = ManageFavouritesDialog(_favourites())
        opened = self._opened(dialog)
        _tree_item(dialog, 1).setSelected(True)

        dialog.open_selected()

        # Song its own; Live's Gig in a new window
        assert opened == [(["Song"], [["Gig"]])]

    def test_double_clicked_opened(self):
        dialog = ManageFavouritesDialog(_favourites())
        opened = self._opened(dialog)

        item = _tree_item(dialog, 1, 1)
        dialog.tree.itemDoubleClicked.emit(item, 0)

        assert opened == [(["Gig"], [])]

    def test_videos_and_folders_together_each_once_in_order(self):
        dialog = ManageFavouritesDialog(_favourites())
        opened = self._opened(dialog)
        _tree_item(dialog, 1, 0).setSelected(True)
        _tree_item(dialog, 1, 1).setSelected(True)
        _tree_item(dialog, 1).setSelected(True)
        _tree_item(dialog, 0).setSelected(True)

        dialog.open_selected()

        # those within Music go with it: Live in a window of its own once
        assert opened == [(["Top", "Song"], [["Gig"]])]

    def test_a_folder_of_folders_alone_opens_them_apart(self):
        favourites = Favourites(
            [
                FavouriteFolder(
                    name="Playlists",
                    items=[
                        FavouriteFolder(name="One", items=[_video("a"), _video("b")]),
                        FavouriteFolder(
                            name="Two",
                            items=[
                                _video("c"),
                                FavouriteFolder(name="Deep", items=[_video("d")]),
                            ],
                        ),
                        FavouriteFolder(name="Empty"),
                    ],
                )
            ]
        )
        dialog = ManageFavouritesDialog(favourites)
        opened = self._opened(dialog)
        _tree_item(dialog, 0).setSelected(True)

        assert dialog.open_button.isEnabled()
        dialog.open_selected()

        assert opened == [([], [["a", "b"], ["c"], ["d"]])]

    def test_opened_as_renamed(self):
        dialog = ManageFavouritesDialog(_favourites())
        videos = []
        dialog.open_requested.connect(lambda here, _apart: videos.extend(here))
        _tree_item(dialog, 0).setText(0, "Renamed")
        _tree_item(dialog, 0).setSelected(True)

        dialog.open_selected()

        assert videos[0].name == "Renamed"
        assert videos[0].loops == [(1000, 2000)]

    def test_open_only_with_something_to_open(self):
        dialog = ManageFavouritesDialog(_favourites())
        opened = self._opened(dialog)

        assert not dialog.open_button.isEnabled()

        _tree_item(dialog, 2).setSelected(True)
        assert not dialog.open_button.isEnabled()
        dialog.open_selected()
        assert opened == []

        _tree_item(dialog, 1).setSelected(True)
        assert dialog.open_button.isEnabled()

    def test_rename_and_remove_with_something_picked(self):
        dialog = ManageFavouritesDialog(_favourites())

        assert not dialog.remove_button.isEnabled()

        _tree_item(dialog, 0).setSelected(True)
        assert dialog.rename_button.isEnabled()

        _tree_item(dialog, 1).setSelected(True)
        assert not dialog.rename_button.isEnabled()
        assert dialog.remove_button.isEnabled()
