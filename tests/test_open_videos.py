"""Opening videos from the menu with nothing open, and the folder the file
dialogs open in: where videos were last opened or added from, the next
time the player starts too."""

from types import SimpleNamespace

import pytest

from gridplayer.params.actions import ACTIONS
from gridplayer.params.menu import SECTIONS
from gridplayer.player.managers import add_videos as module
from gridplayer.utils.command_helpers import NOT
from tests.conftest import StoredSettings


class _FakeFileDialog:
    """The files dialog: the folder it was opened in, and what is picked."""

    ExistingFiles = object()
    opened_in = []
    picked = []
    folder = ""

    def __init__(self, parent=None, caption="", directory=""):
        _FakeFileDialog.opened_in.append(directory)

    def setFileMode(self, _mode):
        pass

    def setNameFilters(self, _filters):
        pass

    def exec(self):
        return bool(_FakeFileDialog.picked)

    def selectedFiles(self):
        return list(_FakeFileDialog.picked)

    @staticmethod
    def getExistingDirectory(parent=None, caption="", directory=""):
        _FakeFileDialog.opened_in.append(directory)
        return _FakeFileDialog.folder


@pytest.fixture
def stored(monkeypatch):
    stored = StoredSettings()
    monkeypatch.setattr(module, "Settings", lambda: stored)
    return stored


@pytest.fixture
def dialog(monkeypatch):
    _FakeFileDialog.opened_in = []
    _FakeFileDialog.picked = []
    _FakeFileDialog.folder = ""
    monkeypatch.setattr(module, "QFileDialog", _FakeFileDialog)
    return _FakeFileDialog


@pytest.fixture
def added():
    return []


@pytest.fixture
def manager(added):
    return SimpleNamespace(
        parent=lambda: None,
        add_media=added.extend,
    )


def _add_videos(manager):
    module.AddVideosManager.cmd_add_videos(manager)


def _add_folder(manager):
    module.AddVideosManager.cmd_add_folder(manager)


class TestTheMenuWithNothingOpen:
    def test_open_videos_first_in_it(self):
        """The first of what is there with no video open."""

        assert SECTIONS["playlist"][0] == "Open Videos"

    def test_only_while_nothing_is_open(self):
        show_if = ACTIONS["Open Videos"]["show_if"]

        assert isinstance(show_if, NOT)
        assert show_if.arg == "is_videos"

    def test_the_same_as_add_files(self):
        assert ACTIONS["Open Videos"]["func"] == ACTIONS["Add - Files"]["func"]


class TestWhereTheDialogOpens:
    def test_where_it_likes_the_first_time(self, stored, dialog, manager):
        _add_videos(manager)

        assert dialog.opened_in == [""]

    def test_the_folder_of_the_files_picked_kept(
        self, stored, dialog, manager, added, tmp_path
    ):
        video = tmp_path / "shows" / "a.mp4"
        video.parent.mkdir()
        video.touch()
        dialog.picked = [str(video)]

        _add_videos(manager)

        assert added == [str(video)]
        assert stored.get("player/last_open_dir") == str(video.parent)

    def test_opened_there_the_next_time(self, stored, dialog, manager, tmp_path):
        stored.set("player/last_open_dir", str(tmp_path))

        _add_videos(manager)

        assert dialog.opened_in == [str(tmp_path)]

    def test_nothing_picked_nothing_kept(self, stored, dialog, manager, tmp_path):
        stored.set("player/last_open_dir", str(tmp_path))

        _add_videos(manager)

        assert stored.get("player/last_open_dir") == str(tmp_path)

    def test_one_gone_since_is_the_dialogs_own(self, stored, dialog, manager, tmp_path):
        stored.set("player/last_open_dir", str(tmp_path / "gone"))

        _add_videos(manager)

        assert dialog.opened_in == [""]

    def test_add_folder_opens_there_and_keeps_the_one_it_is_in(
        self, stored, dialog, manager, added, tmp_path
    ):
        stored.set("player/last_open_dir", str(tmp_path))
        season = tmp_path / "season 1"
        season.mkdir()
        dialog.folder = str(season)

        _add_folder(manager)

        assert dialog.opened_in == [str(tmp_path)]
        assert added == [str(season)]
        assert stored.get("player/last_open_dir") == str(tmp_path)

    def test_files_and_folders_share_it(self, stored, dialog, manager, tmp_path):
        video = tmp_path / "a.mp4"
        video.touch()
        dialog.picked = [str(video)]

        _add_videos(manager)
        _add_folder(manager)

        assert dialog.opened_in == ["", str(tmp_path)]
