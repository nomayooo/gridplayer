"""Favourites shared by every window of the player: folders made in one
found in the others, and none written over by a window that read them
before; and the folder the last was saved into offered for the next."""

from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from gridplayer.dialogs.favourites import (
    AddAllFavouritesDialog,
    AddFavouriteDialog,
    ImportPlaylistsDialog,
)
from gridplayer.models.favourites import FavouriteFolder, Favourites, FolderNames
from gridplayer.player.managers import favourites as manager_module
from gridplayer.settings import default_value
from tests.test_favourites import (
    NEW,
    _block,
    _favourites,
    _grid_of,
    _manager,
    _typed,
    _video,
    undated,  # noqa: F401 (autouse here too)
)


class _Disk:
    """The settings file the windows share."""

    def __init__(self):
        self.values = {}


class _WindowSettings:
    """A window's settings, as QSettings keeps them: what it read last until
    it reads the file again; what it sets written there on a sync."""

    def __init__(self, disk: _Disk):
        self._disk = disk
        self._read = dict(disk.values)
        self._unsaved = {}

    def get(self, key):
        value = self._unsaved.get(key, self._read.get(key))
        return default_value(key) if value is None else value

    def set(self, key, value):
        self._unsaved[key] = value

    def sync(self):
        self._disk.values.update(self._unsaved)
        self._unsaved = {}
        self._read = dict(self._disk.values)

    def sync_get(self, key):
        self.sync()
        return self.get(key)


@pytest.fixture
def disk():
    return _Disk()


def _names(menu):
    return [item["title"] for item in menu]


def _add_into(monkeypatch, folder, made=()):
    """The Add window answered: into the folder at this place, after making
    these folders in it, each named and put where the window puts it."""

    def ask(favourites, **kwargs):
        # into a copy, as the window makes them
        favourites = favourites.model_copy(deep=True)
        for parent, name in made:
            favourites.add(parent, FavouriteFolder(name=name))
        return favourites, folder, "Clip"

    asked = Mock(side_effect=ask)
    monkeypatch.setattr(manager_module.AddFavouriteDialog, "ask", asked)

    return asked


class TestFoundInEveryWindow:
    def test_saved_in_one_found_in_another_opened_before(self, disk, monkeypatch):
        first = _WindowSettings(disk)
        second = _WindowSettings(disk)
        in_use = {"settings": first}
        monkeypatch.setattr(manager_module, "Settings", lambda: in_use["settings"])

        menu_of_second = _manager()
        in_use["settings"] = second
        assert menu_of_second.menu_generator_favourites() == []

        in_use["settings"] = first
        _add_into(monkeypatch, (0, 0), made=[((), "Music"), ((0,), "Live")])
        _manager(active=_block()).cmd_add_to_favourites()

        in_use["settings"] = second
        assert _names(menu_of_second.menu_generator_favourites()) == ["Music"]
        in_music = menu_of_second.menu_generator_favourites_folder((0,))
        assert in_music[0]["title"] == "Live"


@pytest.fixture
def two_windows(disk, monkeypatch):
    """Two windows, each with settings of its own on the same file, and
    which of them is the one in use."""

    state = SimpleNamespace(
        first=_WindowSettings(disk), second=_WindowSettings(disk), disk=disk
    )
    state.in_use = state.first
    monkeypatch.setattr(manager_module, "Settings", lambda: state.in_use)

    return state


class TestNotWrittenOver:
    def test_what_another_saved_while_asked(self, two_windows, monkeypatch):
        def ask(favourites, **kwargs):
            # meanwhile, in the other window
            two_windows.in_use = two_windows.second
            _add_into(monkeypatch, (0,), made=[((), "From the other")])
            _manager(
                active=_block(uri=NEW.with_name("other.mp4"))
            ).cmd_add_to_favourites()
            two_windows.in_use = two_windows.first

            return favourites, (), "Clip"

        monkeypatch.setattr(manager_module.AddFavouriteDialog, "ask", ask)

        _manager(active=_block()).cmd_add_to_favourites()

        kept = two_windows.disk.values["favourites"]
        assert [item.name for item in kept.root] == ["From the other", "Clip"]
        assert [item.name for item in kept.root[0].items] == ["Clip"]

    def test_the_folder_picked_found_where_it_is_now(self, two_windows, monkeypatch):
        two_windows.disk.values["favourites"] = Favourites(
            [FavouriteFolder(name="A"), FavouriteFolder(name="B")]
        )

        def ask(favourites, **kwargs):
            # meanwhile "A" removed in the other window: "B" is first now
            two_windows.disk.values["favourites"] = Favourites(
                [FavouriteFolder(name="B")]
            )
            return favourites, (1,), "Clip"

        monkeypatch.setattr(manager_module.AddFavouriteDialog, "ask", ask)

        _manager(active=_block()).cmd_add_to_favourites()

        kept = two_windows.disk.values["favourites"]
        assert [(f.name, [v.name for v in f.items]) for f in kept.root] == [
            ("B", ["Clip"])
        ]

    def test_folders_made_while_asked_kept_if_not_picked(
        self, two_windows, monkeypatch
    ):
        _add_into(monkeypatch, (), made=[((), "Empty one"), ((0,), "Within")])

        _manager(active=_block()).cmd_add_to_favourites()

        kept = two_windows.disk.values["favourites"]
        assert kept.folders()[1:] == [
            ((0,), ["Empty one"]),
            ((0, 0), ["Empty one", "Within"]),
        ]


@pytest.fixture
def stored(monkeypatch):
    values = {}
    settings = SimpleNamespace(
        get=lambda key: values.get(key, default_value(key)),
        sync_get=lambda key: values.get(key, default_value(key)),
        set=values.__setitem__,
        sync=lambda: None,
    )
    monkeypatch.setattr(manager_module, "Settings", lambda: settings)
    values["favourites"] = _favourites()

    return values


class TestTheLastFolderOffered:
    def test_the_next_one_offered_where_the_last_went(self, stored, monkeypatch):
        asked = _add_into(monkeypatch, (1, 1))

        _manager(active=_block()).cmd_add_to_favourites()
        assert stored["favourites/last_folder"] == FolderNames(["Music", "Live"])

        _manager(active=_block(uri=NEW.with_name("next.mp4"))).cmd_add_to_favourites()
        assert asked.call_args.kwargs["folder"] == (1, 1)

    def test_found_by_name_when_moved(self, stored, monkeypatch):
        stored["favourites/last_folder"] = FolderNames(["Music", "Live"])
        stored["favourites"].root.insert(0, FavouriteFolder(name="New first"))
        asked = _add_into(monkeypatch, ())

        _manager(active=_block()).cmd_add_to_favourites()

        assert asked.call_args.kwargs["folder"] == (2, 1)

    def test_the_top_when_it_is_gone(self, stored, monkeypatch):
        stored["favourites/last_folder"] = FolderNames(["Removed"])
        asked = _add_into(monkeypatch, ())

        _manager(active=_block()).cmd_add_to_favourites()

        assert asked.call_args.kwargs["folder"] == ()

    def test_one_already_a_favourite_offered_its_own(self, stored, monkeypatch):
        stored["favourites/last_folder"] = FolderNames(["Music", "Live"])
        stored["favourites"].root.append(
            FavouriteFolder(name="Mine", items=[_video("Kept", path=NEW)])
        )
        asked = _add_into(monkeypatch, ())

        _manager(active=_block()).cmd_add_to_favourites()

        assert asked.call_args.kwargs["folder"] == (3,)

    def test_not_when_thought_better_of(self, stored, monkeypatch):
        monkeypatch.setattr(
            manager_module.AddFavouriteDialog, "ask", Mock(return_value=None)
        )

        _manager(active=_block()).cmd_add_to_favourites()

        assert "favourites/last_folder" not in stored

    def test_add_all_offered_it_and_remembers_it(self, stored, monkeypatch):
        stored["favourites/last_folder"] = FolderNames(["Music"])
        asked = Mock(side_effect=lambda favourites, **_: (favourites, (2,)))
        monkeypatch.setattr(manager_module.AddAllFavouritesDialog, "ask", asked)

        _grid_of(_block()).cmd_add_all_to_favourites()

        assert asked.call_args.kwargs["folder"] == (1,)
        assert stored["favourites/last_folder"] == FolderNames(["Empty"])

    def test_import_offered_it_too(self, stored, monkeypatch, tmp_path):
        stored["favourites/last_folder"] = FolderNames(["Music"])
        monkeypatch.setattr(
            manager_module.QFileDialog,
            "getOpenFileNames",
            lambda *_a, **_k: ([str(tmp_path / "list.gpls")], ""),
        )
        asked = Mock(return_value=None)
        monkeypatch.setattr(manager_module.ImportPlaylistsDialog, "ask", asked)

        _manager().cmd_import_playlists()

        assert asked.call_args.kwargs["folder"] == (1,)

    def test_kept_with_the_settings_and_read_back(self):
        kept = FolderNames(["Music", "Live"])

        assert FolderNames.model_validate_json(kept.model_dump_json()) == kept


class TestTheWindowsPickIt:
    def test_add_all(self):
        dialog = AddAllFavouritesDialog(
            _favourites(), count=1, left_out=0, folder=(1, 1)
        )

        assert dialog.selected_folder == (1, 1)

    def test_import(self):
        dialog = ImportPlaylistsDialog(_favourites(), names=["List"], folder=(2,))

        assert dialog.selected_folder == (2,)

    def test_add(self):
        dialog = AddFavouriteDialog(_favourites(), name="Clip", loops=0, folder=(1,))

        assert dialog.selected_folder == (1,)

    def test_a_folder_made_in_the_window_picked(self, monkeypatch):
        dialog = AddAllFavouritesDialog(_favourites(), count=1, left_out=0, folder=(1,))
        _typed(monkeypatch, "New")

        dialog.new_folder()

        assert dialog.selected_folder == (1, 2)


class TestFindingAndMakingFolders:
    def test_found_by_names(self):
        assert _favourites().folder_named(["Music", "Live"]) == (1, 1)
        assert _favourites().folder_named([]) == ()
        assert _favourites().folder_named(["Live"]) is None

    def test_where_given_if_still_there(self):
        twins = Favourites([FavouriteFolder(name="Same"), FavouriteFolder(name="Same")])

        assert twins.folder_named(["Same"]) == (0,)
        assert twins.folder_named(["Same"], near=(1,)) == (1,)
        assert twins.folder_named(["Same"], near=(5,)) == (0,)

    def test_made_down_to_it_those_there_kept(self):
        favourites = _favourites()

        assert favourites.make_folder(["Music", "New", "Deeper"], added=None) == (
            1,
            2,
            0,
        )
        assert favourites.folder_named(["Music", "New", "Deeper"]) == (1, 2, 0)
        assert favourites.make_folder(["Music"], added=None) == (1,)
        assert len(favourites.root) == 3


class TestFoldersOfTheSameName:
    """A folder made in the one picked, when another has the same name:
    into the one picked, none of them copied."""

    @pytest.fixture
    def twins(self, stored, monkeypatch):
        stored["favourites"] = Favourites(
            [
                FavouriteFolder(name="Music"),
                FavouriteFolder(name="Music", items=[FavouriteFolder(name="Live")]),
            ]
        )
        _typed(monkeypatch, "New")

        def answered(self):
            # the second "Music"'s "Live" picked, a folder made in it
            self.folder.setCurrentIndex(3)
            self.new_folder()
            return True

        monkeypatch.setattr(AddAllFavouritesDialog, "exec", answered)

        return stored

    def test_made_in_the_one_picked(self, twins):
        _grid_of(_block()).cmd_add_all_to_favourites()

        assert twins["favourites"].folders() == [
            ((), []),
            ((0,), ["Music"]),
            ((1,), ["Music"]),
            ((1, 0), ["Music", "Live"]),
            ((1, 0, 0), ["Music", "Live", "New"]),
        ]
        assert [v.name for v in twins["favourites"].items_at((1, 0, 0))] == [
            "Shown title"
        ]

    def test_two_of_a_name_made_both_kept(self, stored, monkeypatch):
        _typed(monkeypatch, "Twin")

        def answered(self):
            self.new_folder()
            self.folder.setCurrentIndex(0)
            self.new_folder()
            return True

        monkeypatch.setattr(AddAllFavouritesDialog, "exec", answered)

        _grid_of(_block()).cmd_add_all_to_favourites()

        assert [f.name for f in stored["favourites"].root[-2:]] == ["Twin", "Twin"]
        assert stored["favourites"].root[-1].items
