"""Cells picked out and moved to a new window: the picking, the handing over
to another player started for them, and that player taking them in.

The real-app scenario move_to_new_window drives it in the player itself.
"""

import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, Mock
from uuid import uuid4

import pytest

from gridplayer.main import init_cli
from gridplayer.models.media_list import MediaList
from gridplayer.models.moved_cells import MovedCell, MovedCells
from gridplayer.models.video import Video, VideoBlockMime
from gridplayer.params import env
from gridplayer.player.managers import new_window
from gridplayer.player.managers.new_window import NewWindowManager
from gridplayer.utils import new_window as command
from gridplayer.utils.new_window import MOVED_CELLS_ARG, new_window_command

HERE = Path(__file__).resolve()
LIST_HERE = uuid4()


class TestTheCommand:
    @pytest.fixture(autouse=True)
    def _as_from_source(self, monkeypatch):
        monkeypatch.setattr(env, "IS_APPIMAGE", False)
        monkeypatch.setattr(env, "IS_PYINSTALLER", False)
        monkeypatch.setattr(env, "IS_LINUX", False)

    def test_run_from_source_the_same_way(self):
        program, args = new_window_command(Path("/tmp/m.json"))

        assert program == sys.executable
        assert args == ["-m", "gridplayer", MOVED_CELLS_ARG, str(Path("/tmp/m.json"))]

    def test_a_built_player_itself(self, monkeypatch):
        monkeypatch.setattr(env, "IS_PYINSTALLER", True)

        program, args = new_window_command(Path("m.json"))

        assert program == sys.executable
        assert args == [MOVED_CELLS_ARG, "m.json"]

    def test_an_appimage_by_the_appimage(self, monkeypatch):
        monkeypatch.setattr(env, "IS_APPIMAGE", True)
        monkeypatch.setattr(env, "IS_PYINSTALLER", True)
        monkeypatch.setenv("APPIMAGE", "/apps/GridPlayer.AppImage")

        program, _ = new_window_command(Path("m.json"))

        assert program == "/apps/GridPlayer.AppImage"

    @pytest.mark.parametrize(
        ("platform", "passed"), [("xcb", True), ("wayland", True), ("offscreen", False)]
    )
    def test_on_the_display_server_this_one_runs_on(
        self, monkeypatch, platform, passed
    ):
        monkeypatch.setattr(env, "IS_LINUX", True)
        monkeypatch.setattr(command.env, "QT_PLATFORM", platform)

        _, args = new_window_command(Path("m.json"))

        assert (["--platform", platform] == args[2:4]) is passed


class TestTheCommandLine:
    @pytest.fixture(autouse=True)
    def _kept(self, monkeypatch):
        monkeypatch.setattr(sys, "argv", ["gridplayer"])
        monkeypatch.setattr(env, "MOVED_CELLS_FILE", None)

    def test_the_cells_file_is_taken_apart_from_the_files(self):
        init_cli.init_cli_args([MOVED_CELLS_ARG, "/tmp/m.json"])

        assert env.MOVED_CELLS_FILE == Path("/tmp/m.json")
        assert sys.argv[1:] == []

    def test_none_without_it(self):
        init_cli.init_cli_args(["a.mp4"])

        assert env.MOVED_CELLS_FILE is None
        assert sys.argv[1:] == ["a.mp4"]


def _block(name, loops=(), media_list=None):
    video = Video(uri=HERE, title=name, loops=list(loops))
    block = SimpleNamespace(
        id=f"block-{name}",
        is_selected=False,
        video_params=video,
        media_list=media_list,
        close=Mock(),
    )
    block.drag_data = VideoBlockMime(id=block.id, video=video)
    return block


class _Blocks(list):
    def by_id(self, block_id):
        return next((b for b in self if b.id == block_id), None)

    def by_video_id(self, video_id):
        return next((b for b in self if str(b.video_params.id) == str(video_id)), None)

    def blocks_for_ids(self, video_ids):
        return [b for i in video_ids if (b := self.by_video_id(i)) is not None]


@pytest.fixture
def blocks():
    return _Blocks(
        [_block("a.mp4"), _block("b.mp4", loops=[(1000, 2000)]), _block("c.mp4")]
    )


@pytest.fixture
def manager(blocks):
    commands = MagicMock()
    commands.layout_order = lambda: [str(b.video_params.id) for b in blocks]

    ctx = SimpleNamespace(
        active_block=blocks[0],
        video_blocks=blocks,
        commands=commands,
        lists=MagicMock(),
        bookmarks=MagicMock(),
    )

    manager = NewWindowManager(context=ctx)
    manager.errors = []
    manager.error.connect(manager.errors.append)

    return manager


def _select(manager, *blocks):
    for block in blocks:
        manager._ctx.active_block = block
        manager.cmd_toggle_cell_selected()


class TestPicking:
    def test_picked_out_and_marked(self, manager, blocks):
        _select(manager, blocks[0], blocks[2])

        assert [b.is_selected for b in blocks] == [True, False, True]
        assert manager.is_any_cells_selected()

    def test_picked_again_let_go(self, manager, blocks):
        _select(manager, blocks[0], blocks[0])

        assert not blocks[0].is_selected
        assert not manager.is_any_cells_selected()

    def test_whether_the_active_one_is(self, manager, blocks):
        _select(manager, blocks[1])

        manager._ctx.active_block = blocks[1]
        assert manager.is_active_cell_selected()
        manager._ctx.active_block = blocks[0]
        assert not manager.is_active_cell_selected()

    def test_all_let_go(self, manager, blocks):
        _select(manager, blocks[0], blocks[1])

        manager.cmd_clear_cell_selection()

        assert not any(b.is_selected for b in blocks)
        assert not manager.is_any_cells_selected()

    def test_one_closed_is_no_longer_picked(self, manager, blocks):
        _select(manager, blocks[0])
        blocks.pop(0)

        manager.forget_cells_gone()

        assert manager._selected == []


@pytest.fixture
def started(monkeypatch):
    calls = []

    def start_detached(program, args):
        calls.append((program, args))
        return True, 1

    monkeypatch.setattr(new_window.QProcess, "startDetached", start_detached)

    return calls


def _handed_over(started) -> tuple[Path, MovedCells]:
    _, args = started[-1]
    path = Path(args[args.index(MOVED_CELLS_ARG) + 1])
    return path, MovedCells.model_validate_json(path.read_bytes())


class TestMovingOut:
    def test_the_ones_picked_in_the_grids_order(self, manager, blocks, started):
        _select(manager, blocks[2], blocks[1])

        manager.cmd_move_to_new_window()

        path, moved = _handed_over(started)
        assert [m.cell.id for m in moved.cells] == [blocks[1].id, blocks[2].id]
        assert moved.cells[0].cell.video.loops == [(1000, 2000)]
        path.unlink()

    def test_gone_from_here_and_let_go(self, manager, blocks, started):
        _select(manager, blocks[0], blocks[1])

        manager.cmd_move_to_new_window()

        blocks[0].close.assert_called_once_with()
        blocks[1].close.assert_called_once_with()
        blocks[2].close.assert_not_called()
        assert not blocks[0].is_selected
        _handed_over(started)[0].unlink()

    def test_the_active_one_with_none_picked(self, manager, blocks, started):
        manager._ctx.active_block = blocks[2]

        manager.cmd_move_to_new_window()

        path, moved = _handed_over(started)
        assert [m.cell.id for m in moved.cells] == [blocks[2].id]
        path.unlink()

    def test_with_its_list(self, manager, blocks, started):
        media_list = MediaList(name="Clips")
        blocks[0].media_list = media_list
        _select(manager, blocks[0])

        manager.cmd_move_to_new_window()

        path, moved = _handed_over(started)
        assert moved.cells[0].media_list == media_list
        path.unlink()

    def test_kept_here_when_no_window_could_start(self, manager, blocks, monkeypatch):
        tried = []

        def start_detached(program, args):
            tried.append(Path(args[args.index(MOVED_CELLS_ARG) + 1]))
            return False, 0

        monkeypatch.setattr(new_window.QProcess, "startDetached", start_detached)
        _select(manager, blocks[0])

        manager.cmd_move_to_new_window()

        blocks[0].close.assert_not_called()
        assert blocks[0].is_selected
        assert len(manager.errors) == 1
        assert not tried[0].exists()

    def test_nothing_with_no_cell(self, manager, started):
        manager._ctx.active_block = None

        manager.cmd_move_to_new_window()

        assert started == []


@pytest.fixture
def receiver(tmp_path):
    taken = _Blocks()

    commands = MagicMock()
    ctx = SimpleNamespace(
        video_blocks=taken,
        commands=commands,
        lists=MagicMock(),
        bookmarks=MagicMock(),
    )
    ctx.lists.add.side_effect = lambda media_list: media_list.model_copy(
        update={"id": LIST_HERE}
    )

    manager = NewWindowManager(context=ctx)
    manager.taken = []

    def take(videos):
        manager.taken.append(videos)
        for video in videos:
            block = _block(video.title or "")
            block.video_params = video
            taken.append(block)

    manager.cells_moved_in.connect(take)
    manager.errors = []
    manager.error.connect(manager.errors.append)

    return manager


def _moved_file(tmp_path, *cells) -> Path:
    path = tmp_path / "moved.json"
    path.write_text(MovedCells(cells=list(cells)).model_dump_json())
    return path


class TestTakingIn:
    def test_each_as_it_was_and_the_file_let_go(self, receiver, tmp_path):
        video = Video(uri=HERE, loops=[(1000, 2000)], current_position=1500)
        path = _moved_file(
            tmp_path, MovedCell(cell=VideoBlockMime(id="x", video=video))
        )

        receiver.open_moved_cells(path)

        ((taken,),) = receiver.taken
        assert taken.uri == HERE
        assert isinstance(taken.uri, Path)
        assert (taken.loops, taken.current_position) == ([(1000, 2000)], 1500)
        assert not path.exists()

    def test_closed_without_asking(self, receiver, tmp_path):
        path = _moved_file(
            tmp_path, MovedCell(cell=VideoBlockMime(id="x", video=Video(uri=HERE)))
        )

        receiver.open_moved_cells(path)

        receiver._ctx.commands.set_playlist_scratch.assert_called_once_with()

    def test_with_its_bookmarks_and_list(self, receiver, tmp_path):
        from gridplayer.models.bookmark import Bookmark

        bookmarks = [Bookmark(time_ms=1000, name="Here")]
        cell = VideoBlockMime(id="x", video=Video(uri=HERE), bookmarks=bookmarks)
        path = _moved_file(tmp_path, MovedCell(cell=cell, media_list=MediaList()))

        receiver.open_moved_cells(path)

        ((taken,),) = receiver.taken
        assert taken.list_id == LIST_HERE
        receiver._ctx.bookmarks.add.assert_called_once_with(HERE, taken.id, bookmarks)

    def test_a_file_that_cannot_be_read_is_said(self, receiver, tmp_path):
        path = tmp_path / "moved.json"
        path.write_text("not cells")

        receiver.open_moved_cells(path)

        assert receiver.taken == []
        assert len(receiver.errors) == 1
        assert not path.exists()
