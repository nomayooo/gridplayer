"""Files deleted for good from the player: which, asked first, the cells
showing them closed, and a file still held tried again.

The real-app scenario delete_file drives it in the player itself.
"""

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, Mock

import pytest
from PyQt5.QtWidgets import QMessageBox

from gridplayer.models.video import Video
from gridplayer.player.managers import delete_files
from gridplayer.player.managers.delete_files import DeleteFilesManager


def _block(uri):
    return SimpleNamespace(video_params=Video(uri=uri), close=Mock())


@pytest.fixture
def files(tmp_path):
    paths = [tmp_path / "a.mp4", tmp_path / "b.mp4", tmp_path / "c.mp4"]
    for path in paths:
        path.write_bytes(b"video")
    return paths


@pytest.fixture
def blocks(files):
    return [_block(files[0]), _block(files[1]), _block(files[2])]


@pytest.fixture
def selected():
    return []


@pytest.fixture
def manager(blocks, selected):
    commands = MagicMock()
    commands.selected_cells = lambda: list(selected)

    ctx = SimpleNamespace(
        active_block=blocks[0],
        video_blocks=list(blocks),
        commands=commands,
        seek_preview=Mock(),
    )

    manager = DeleteFilesManager(context=ctx)
    manager.errors = []
    manager.error.connect(manager.errors.append)

    return manager


@pytest.fixture
def answered(monkeypatch):
    """Each "are you sure?" answered as set, and what it asked kept."""

    asked = SimpleNamespace(answer=QMessageBox.Yes, questions=[])

    def question(_parent, _title, text, **_kwargs):
        asked.questions.append(text)
        return asked.answer

    monkeypatch.setattr(delete_files.QCustomMessageBox, "question", question)

    return asked


class TestWhich:
    def test_the_active_ones(self, manager, blocks, files, answered):
        manager.cmd_delete_files()

        assert [f.exists() for f in files] == [False, True, True]
        blocks[0].close.assert_called_once_with()
        blocks[1].close.assert_not_called()
        assert answered.questions == ['Permanently delete "a.mp4"?']

    def test_let_go_of_by_the_seek_preview_first(self, manager, files, answered):
        let_go = []
        manager._ctx.seek_preview.let_go_of.side_effect = lambda path: let_go.append(
            (path, path.exists())
        )

        manager.cmd_delete_files()

        assert let_go == [(files[0], True)]
        assert not files[0].exists()

    def test_the_picked_ones_over_the_active_one(
        self, manager, blocks, files, selected, answered
    ):
        selected.extend([blocks[1], blocks[2]])

        manager.cmd_delete_files()

        assert [f.exists() for f in files] == [True, False, False]
        blocks[0].close.assert_not_called()
        assert answered.questions == ["Permanently delete 2 files?"]
        manager._ctx.commands.clear_cell_selection.assert_called_once_with()

    def test_every_cell_showing_it_closed(self, manager, blocks, files, answered):
        again = _block(files[0])
        manager._ctx.video_blocks.append(again)

        manager.cmd_delete_files()

        assert not files[0].exists()
        again.close.assert_called_once_with()
        assert answered.questions == ['Permanently delete "a.mp4"?']

    def test_not_a_stream(self, manager, answered):
        manager._ctx.active_block = SimpleNamespace(
            video_params=Video(uri="https://example.com/a.m3u8"), close=Mock()
        )

        assert not manager.is_any_to_delete()

        manager.cmd_delete_files()

        assert answered.questions == []
        manager._ctx.active_block.close.assert_not_called()

    def test_nothing_with_no_cell(self, manager, answered):
        manager._ctx.active_block = None

        assert not manager.is_any_to_delete()

        manager.cmd_delete_files()

        assert answered.questions == []


class TestAsking:
    def test_kept_when_not_sure(self, manager, blocks, files, answered):
        answered.answer = QMessageBox.No

        manager.cmd_delete_files()

        assert files[0].exists()
        blocks[0].close.assert_not_called()


class TestDeleting:
    def test_one_still_held_tried_again(self, manager, files, answered, monkeypatch):
        held = {"times": 2}
        unlink = Path.unlink

        def held_unlink(path, missing_ok=False):
            if held["times"]:
                held["times"] -= 1
                raise PermissionError(13, "in use")
            unlink(path, missing_ok=missing_ok)

        monkeypatch.setattr(Path, "unlink", held_unlink)

        manager.cmd_delete_files()
        assert files[0].exists()
        assert manager._retry_timer.isActive()

        manager._delete_pending()
        manager._delete_pending()

        assert not files[0].exists()
        assert not manager._retry_timer.isActive()
        assert manager.errors == []

    def test_one_held_for_good_said(self, manager, files, answered, monkeypatch):
        def held_unlink(_path, missing_ok=False):
            raise PermissionError(13, "in use")

        monkeypatch.setattr(Path, "unlink", held_unlink)

        manager.cmd_delete_files()
        for _ in range(delete_files.RETRY_TIMES):
            manager._delete_pending()

        assert len(manager.errors) == 1
        assert '"a.mp4"' in manager.errors[0]
        assert not manager._retry_timer.isActive()

    def test_one_gone_already_is_no_error(self, manager, files, answered):
        files[0].unlink()

        manager.cmd_delete_files()

        assert manager.errors == []
