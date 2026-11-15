"""Open Playlist opening where a playlist was last opened from: in every
window, and the next time the player starts too."""

from types import SimpleNamespace

import pytest

from gridplayer.player.managers import playlist as module
from tests.conftest import StoredSettings


class _FakeFileDialog:
    """The dialog: the folder it was opened in, and what is picked."""

    ExistingFile = object()
    opened_in = []
    picked = []

    def __init__(self, parent=None, caption="", directory=""):
        _FakeFileDialog.opened_in.append(directory)

    def setFileMode(self, _mode):
        pass

    def setNameFilter(self, _filter):
        pass

    def exec(self):
        return bool(_FakeFileDialog.picked)

    def selectedFiles(self):
        return list(_FakeFileDialog.picked)


@pytest.fixture
def stored(monkeypatch):
    stored = StoredSettings()
    monkeypatch.setattr(module, "Settings", lambda: stored)
    return stored


@pytest.fixture
def dialog(monkeypatch):
    _FakeFileDialog.opened_in = []
    _FakeFileDialog.picked = []
    monkeypatch.setattr(module, "QFileDialog", _FakeFileDialog)
    return _FakeFileDialog


@pytest.fixture
def opened():
    return []


@pytest.fixture
def manager(opened):
    return SimpleNamespace(parent=lambda: None, load_playlist_file=opened.append)


def _open(manager):
    module.PlaylistManager.cmd_open_playlist(manager)


def test_where_it_likes_the_first_time(stored, dialog, manager):
    _open(manager)

    assert dialog.opened_in == [""]


def test_the_folder_of_the_one_opened_kept(stored, dialog, manager, opened, tmp_path):
    playlist = tmp_path / "lists" / "mix.gpls"
    playlist.parent.mkdir()
    playlist.touch()
    dialog.picked = [str(playlist)]

    _open(manager)

    assert opened == [playlist]
    assert stored.get("player/last_playlist_dir") == str(playlist.parent)


def test_opened_there_the_next_time(stored, dialog, manager, tmp_path):
    stored.set("player/last_playlist_dir", str(tmp_path))

    _open(manager)

    assert dialog.opened_in == [str(tmp_path)]


def test_nothing_picked_nothing_kept(stored, dialog, manager, tmp_path):
    stored.set("player/last_playlist_dir", str(tmp_path))

    _open(manager)

    assert stored.get("player/last_playlist_dir") == str(tmp_path)


def test_one_gone_since_is_the_dialogs_own(stored, dialog, manager, tmp_path):
    stored.set("player/last_playlist_dir", str(tmp_path / "gone"))

    _open(manager)

    assert dialog.opened_in == [""]
