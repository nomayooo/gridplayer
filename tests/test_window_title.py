"""The window's title: the name of the playlist open, marked while changed
since it was saved, or else of the favourites folder it was opened from,
in this window or a new one."""

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, Mock

import pytest
from PyQt5.QtWidgets import QWidget

from gridplayer.dialogs.favourites import ManageFavouritesDialog
from gridplayer.models.favourites import (
    FavouriteFolder,
    Favourites,
    FavouriteVideo,
    FolderVideos,
    folders_within,
)
from gridplayer.models.moved_cells import MovedCell, MovedCells
from gridplayer.models.video import Video, VideoBlockMime
from gridplayer.player.managers import favourites as favourites_module
from gridplayer.player.managers.favourites import FavouritesManager
from gridplayer.player.managers.new_window import NewWindowManager
from gridplayer.player.managers.playlist import PlaylistManager
from tests.test_favourites import (
    _block,
    _grid_of,
    _tree_item,
    _video,
    undated,  # noqa: F401 (autouse here too)
)
from tests.test_favourites import stored as stored

HERE = Path(__file__).resolve()


@pytest.fixture
def playlists(monkeypatch):
    window = QWidget()
    manager = PlaylistManager(context=SimpleNamespace(), parent=window)
    manager.changed = False
    monkeypatch.setattr(manager, "_playlist_state", lambda: ((), ()))
    monkeypatch.setattr(manager, "_is_playlist_changed", lambda: manager.changed)
    monkeypatch.setattr(manager, "_reset_playlist_session", lambda: None)
    manager.window = window
    yield manager
    manager._title_timer.stop()


class TestTheTitle:
    def test_none_of_its_own_with_nothing_open(self, playlists):
        playlists.update_window_title()

        assert playlists.window.windowTitle() == ""

    def test_the_playlists_name_without_its_extension(self, playlists):
        playlists._set_saved_playlist(Path("/films/My list.gpl"))

        assert playlists.window.windowTitle() == "My list[*]"
        assert not playlists.window.isWindowModified()

    def test_marked_once_changed(self, playlists):
        playlists._set_saved_playlist(Path("/films/My list.gpl"))
        playlists.changed = True

        playlists.update_window_title()

        assert playlists.window.isWindowModified()

    def test_the_name_it_was_opened_from(self, playlists):
        playlists.set_window_name("Music")

        assert playlists.window.windowTitle() == "Music"

    def test_a_playlist_saved_named_instead(self, playlists):
        playlists.set_window_name("Music")

        playlists._set_saved_playlist(Path("/films/Saved.gpl"))

        assert playlists.window.windowTitle() == "Saved[*]"

    def test_none_once_closed(self, playlists):
        playlists.set_window_name("Music")

        playlists.cmd_force_close_playlist()

        assert playlists.window.windowTitle() == ""


# favourites


@pytest.fixture
def folders(stored, tmp_path):
    def fav(name):
        path = tmp_path / f"{name}.mp4"
        path.write_bytes(b"video")
        return FavouriteVideo(name=name, path=path)

    stored["favourites"] = Favourites(
        [
            FavouriteFolder(
                name="Music",
                items=[
                    fav("song"),
                    FavouriteFolder(name="Live", items=[fav("gig")]),
                ],
            ),
            FavouriteFolder(name="Films", items=[FavouriteFolder(name="Old")]),
        ]
    )


def _manager(is_videos=True):
    commands = MagicMock()
    commands.is_videos = lambda: is_videos
    return FavouritesManager(
        context=SimpleNamespace(active_block=None, commands=commands)
    )


class TestFavourites:
    def test_each_folder_within_named(self):
        items = [
            FavouriteFolder(name="A", items=[_video("a")]),
            FavouriteFolder(name="Empty"),
        ]

        found = folders_within(items)

        assert found == [[_video("a")]]
        assert found[0].name == "A"

    def test_a_window_of_its_own_named_after_its_folder(self, folders):
        manager = _manager()

        manager.cmd_open_favourites_folder((0,))

        ((_videos,), kwargs) = manager._ctx.commands.open_in_new_window.call_args
        assert kwargs == {"title": "Live"}

    def test_this_window_named_after_the_folder_if_empty(self, folders):
        manager = _manager(is_videos=False)

        manager.cmd_open_favourites_folder((0,))

        manager._ctx.commands.set_window_name.assert_called_once_with("Music")

    def test_this_one_left_as_it_is_with_videos_open(self, folders):
        manager = _manager(is_videos=True)

        manager.cmd_open_favourites_folder((0,))

        manager._ctx.commands.set_window_name.assert_not_called()

    def test_videos_alone_name_nothing(self, folders):
        manager = _manager(is_videos=False)

        manager.open_favourites([_video("a")], [])

        manager._ctx.commands.set_window_name.assert_not_called()


def _opened(dialog):
    opened = []
    dialog.open_requested.connect(
        lambda here, apart: opened.append(
            (getattr(here, "name", None), [getattr(w, "name", None) for w in apart])
        )
    )
    return opened


class TestManageFavourites:
    @pytest.fixture
    def dialog(self):
        return ManageFavouritesDialog(
            Favourites(
                [
                    _video("Loose"),
                    FavouriteFolder(
                        name="One",
                        items=[
                            _video("a"),
                            FavouriteFolder(name="Inner", items=[_video("i")]),
                        ],
                    ),
                    FavouriteFolder(name="Two", items=[_video("c")]),
                ]
            )
        )

    def test_one_folder_picked_names_what_opens_here(self, dialog):
        opened = _opened(dialog)
        _tree_item(dialog, 1).setSelected(True)

        dialog.open_selected()

        assert opened == [("One", ["Inner"])]

    def test_several_each_its_own(self, dialog):
        opened = _opened(dialog)
        _tree_item(dialog, 1).setSelected(True)
        _tree_item(dialog, 2).setSelected(True)

        dialog.open_selected()

        assert opened == [(None, ["One", "Inner", "Two"])]

    def test_a_video_picked_with_it_no_name_here(self, dialog):
        opened = _opened(dialog)
        _tree_item(dialog, 0).setSelected(True)
        _tree_item(dialog, 2).setSelected(True)

        dialog.open_selected()

        assert opened == [(None, [])]

    def test_the_name_as_renamed_in_it(self, dialog):
        opened = _opened(dialog)
        _tree_item(dialog, 2).setText(0, "Renamed")
        _tree_item(dialog, 2).setSelected(True)

        dialog.open_selected()

        assert opened == [("Renamed", [])]


class TestANewWindow:
    def test_the_name_handed_over(self, monkeypatch, tmp_path):
        started = []
        monkeypatch.setattr(
            "gridplayer.player.managers.new_window.QProcess.startDetached",
            lambda program, args: started.append(args) or True,
        )
        manager = NewWindowManager(context=SimpleNamespace(commands=Mock()))

        manager.cmd_open_in_new_window([Video(uri=HERE)], title="Live")

        moved_file = Path(started[0][-1])
        assert MovedCells.model_validate_json(moved_file.read_bytes()).title == "Live"
        moved_file.unlink()

    def test_taken_in_named(self, tmp_path):
        commands = MagicMock()
        ctx = SimpleNamespace(
            commands=commands,
            video_blocks=MagicMock(),
            lists=MagicMock(),
            bookmarks=MagicMock(),
        )
        manager = NewWindowManager(context=ctx)
        path = tmp_path / "moved.json"
        path.write_text(
            MovedCells(
                cells=[MovedCell(cell=VideoBlockMime(id="x", video=Video(uri=HERE)))],
                title="Live",
            ).model_dump_json()
        )

        manager.open_moved_cells(path)

        commands.set_window_name.assert_called_once_with("Live")


def test_a_folders_videos_still_a_list():
    assert FolderVideos([1, 2], "A") == [1, 2]


class TestSavedToAFolder:
    """All the window's videos saved into a folder name the window after it,
    as if opened from it."""

    @pytest.fixture
    def into_music(self, stored, monkeypatch):
        asked = Mock(return_value=(stored["favourites"], (1,)))
        monkeypatch.setattr(favourites_module.AddAllFavouritesDialog, "ask", asked)

    def test_add_all(self, into_music):
        manager = _grid_of(_block(uri=HERE), _block(uri=HERE, title="Two"))

        manager.cmd_add_all_to_favourites()

        manager._ctx.commands.set_window_name.assert_called_once_with("Music")

    def test_a_stream_among_them_left_out_still(self, into_music):
        manager = _grid_of(_block(uri=HERE), _block(uri="https://example.com/v"))

        manager.cmd_add_all_to_favourites()

        manager._ctx.commands.set_window_name.assert_called_once_with("Music")

    def test_all_of_them_picked_out(self, into_music):
        blocks = [_block(uri=HERE), _block(uri=HERE, title="Two")]
        manager = _grid_of(*blocks)
        manager._ctx.commands.selected_cells = lambda: list(blocks)

        manager.cmd_add_to_favourites()

        manager._ctx.commands.set_window_name.assert_called_once_with("Music")

    def test_some_picked_out_name_nothing(self, into_music):
        blocks = [_block(uri=HERE), _block(uri=HERE, title="Two")]
        manager = _grid_of(*blocks)
        manager._ctx.commands.selected_cells = lambda: blocks[:1]

        manager.cmd_add_to_favourites()

        manager._ctx.commands.set_window_name.assert_not_called()

    def test_the_only_video_on_its_own(self, stored, monkeypatch):
        monkeypatch.setattr(
            favourites_module.AddFavouriteDialog,
            "ask",
            Mock(return_value=(stored["favourites"], (2,), "Clip")),
        )
        block = _block(uri=HERE)
        manager = _grid_of(block)
        manager._ctx.active_block = block
        manager._ctx.commands.selected_cells = list

        manager.cmd_add_to_favourites()

        manager._ctx.commands.set_window_name.assert_called_once_with("Empty")

    def test_the_top_names_nothing(self, stored, monkeypatch):
        monkeypatch.setattr(
            favourites_module.AddAllFavouritesDialog,
            "ask",
            Mock(return_value=(stored["favourites"], ())),
        )
        manager = _grid_of(_block(uri=HERE))

        manager.cmd_add_all_to_favourites()

        manager._ctx.commands.set_window_name.assert_not_called()
