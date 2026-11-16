"""Bookmarks remembered by the file they are in, whatever the playlist: kept
in the player's settings as the viewer adds, renames or removes them, and
found again whenever the file is opened, in a playlist or not."""

import json
from types import SimpleNamespace
from uuid import uuid4

import pytest
from PyQt5.QtWidgets import QWidget

from gridplayer.models.bookmark import Bookmark
from gridplayer.models.file_bookmarks import (
    FileBookmarks,
    RememberedBookmarks,
    RememberedFile,
)
from gridplayer.player.managers.bookmarks import BookmarksManager, BookmarksRegistry
from gridplayer.settings import default_value
from gridplayer.utils.bookmarks import file_key

A = [Bookmark(time_ms=10000), Bookmark(time_ms=30000, name="Goal")]
B = [Bookmark(time_ms=20000, name="Kick-off")]


@pytest.fixture
def movie(tmp_path):
    return tmp_path / "movie.mkv"


@pytest.fixture
def other(tmp_path):
    return tmp_path / "other.mkv"


@pytest.fixture
def manager():
    context = SimpleNamespace(
        video_blocks=SimpleNamespace(blocks_for_ids=lambda _ids: []),
        commands=SimpleNamespace(layout_order=list),
    )

    parent = QWidget()
    made = BookmarksManager(context=context, parent=parent)
    made.registry = context.bookmarks
    made.kept_parent = parent

    return made


def _remembered(stored):
    return stored.get("bookmarks/remembered").root


class TestKeptAsTheyAreMade:
    def test_one_added_is_kept_for_its_file(self, manager, movie, remembered_bookmarks):
        manager.registry.set(movie, None, A)

        kept = _remembered(remembered_bookmarks)[file_key(movie)]
        assert (kept.uri, kept.bookmarks) == (movie, A)

    def test_renamed_and_removed_too(self, manager, movie, remembered_bookmarks):
        manager.registry.set(movie, None, A)
        renamed = [A[0], A[1].model_copy(update={"name": "Own goal"})]

        manager.registry.set(movie, None, renamed)
        assert _remembered(remembered_bookmarks)[file_key(movie)].bookmarks == renamed

        manager.registry.set(movie, None, [])
        assert file_key(movie) not in _remembered(remembered_bookmarks)

    def test_each_file_its_own(self, manager, movie, other, remembered_bookmarks):
        manager.registry.set(movie, None, A)
        manager.registry.set(other, None, B)
        manager.registry.set(movie, None, [])

        assert list(_remembered(remembered_bookmarks)) == [file_key(other)]

    def test_another_windows_kept_as_it_left_them(
        self, manager, movie, other, remembered_bookmarks
    ):
        """Read again before each is kept, not written over from what this
        window read before."""

        manager.registry.set(movie, None, A)
        # meanwhile, another window
        another = RememberedBookmarks(dict(_remembered(remembered_bookmarks)))
        another.root[file_key(other)] = RememberedFile(uri=other, bookmarks=B)
        remembered_bookmarks.set("bookmarks/remembered", another)

        manager.registry.set(movie, None, A[:1])

        assert set(_remembered(remembered_bookmarks)) == {
            file_key(movie),
            file_key(other),
        }

    def test_each_cells_own_kept_as_one(self, manager, movie, remembered_bookmarks):
        manager.registry.set_shared(False, ())
        manager.registry.set(movie, uuid4(), A)
        manager.registry.set(movie, uuid4(), B)

        kept = _remembered(remembered_bookmarks)[file_key(movie)].bookmarks
        assert [b.time_ms for b in kept] == [10000, 20000, 30000]

    def test_changed_in_bookmarks_in_playlist_too(
        self, manager, movie, remembered_bookmarks
    ):
        manager.registry.put_entries([FileBookmarks(uri=movie, bookmarks=B)])
        assert _remembered(remembered_bookmarks)[file_key(movie)].bookmarks == B

        manager.registry.remove_entries([FileBookmarks(uri=movie, bookmarks=B)])
        assert file_key(movie) not in _remembered(remembered_bookmarks)


def test_the_settings_default_left_as_it_is(manager, movie):
    manager.registry.set(movie, None, A)

    assert default_value("bookmarks/remembered").root == {}


class TestNotForgottenByWhatIsNotTheViewers:
    @pytest.fixture
    def kept(self, manager, movie, remembered_bookmarks):
        manager.registry.set(movie, None, A)
        return remembered_bookmarks

    def test_another_playlist_opened(self, manager, kept, movie):
        manager.registry.load([], ())
        manager.registry.clear()

        assert _remembered(kept)[file_key(movie)].bookmarks == A

    def test_a_cell_closed(self, manager, kept, movie):
        manager.registry.set_shared(False, ())
        manager.registry.forget_cells_gone(set())

        assert _remembered(kept)[file_key(movie)].bookmarks == A


class TestFoundAgain:
    @pytest.fixture
    def kept(self, manager, movie, remembered_bookmarks):
        manager.registry.set(movie, None, A)
        # another playlist, or none, then the file opened again
        manager.registry.clear()
        return remembered_bookmarks

    def test_the_file_opened_again_has_them(self, manager, kept, movie):
        manager.registry.claim(movie, uuid4())

        assert list(manager.registry.get(movie, None)) == A

    def test_whatever_way_its_path_is_written(self, manager, kept, movie):
        other_case = movie.with_name(movie.name.upper())
        manager.registry.claim(other_case, uuid4())

        assert list(manager.registry.get(other_case, None)) == (
            A if file_key(other_case) == file_key(movie) else []
        )

    def test_with_the_playlists_own_both_kept(self, manager, kept, movie):
        here = [
            Bookmark(time_ms=30000, name="Named here"),
            Bookmark(time_ms=50000),
        ]
        manager.registry.load([FileBookmarks(uri=movie, bookmarks=here)], ())

        manager.registry.claim(movie, uuid4())

        got = list(manager.registry.get(movie, None))
        assert [b.time_ms for b in got] == [10000, 30000, 50000]
        # where both have one, the playlist's is the one kept
        assert got[1].name == "Named here"

    def test_a_cell_keeping_its_own_has_them_too(self, manager, kept, movie):
        manager.registry.set_shared(False, ())
        cell = uuid4()

        manager.registry.claim(movie, cell)

        assert list(manager.registry.get(movie, cell)) == A

    def test_found_as_a_playlist_opens_before_its_cells_do(self, manager, kept, movie):
        """In place before the playlist is taken as it was opened, a stream
        slow to open too: part of what it opened, not a change to ask about
        saving on closing it."""

        manager.set_bookmarks([], [uuid4()], [movie])

        assert list(manager.registry.get(movie, None)) == A

    def test_found_again_is_not_a_change_of_the_viewers(self, manager, kept, movie):
        edits = []
        manager.registry.edited.connect(edits.append)

        manager.registry.claim(movie, uuid4())

        assert edits == []

    def test_none_remembered_none_found(self, manager, other):
        manager.registry.claim(other, uuid4())

        assert manager.registry.get(other, None) == ()


class TestARegistryAlone:
    def test_remembers_nothing_and_finds_nothing(self, movie):
        registry = BookmarksRegistry()

        registry.claim(movie, uuid4())

        assert registry.get(movie, None) == ()


def test_kept_in_the_settings_and_read_back(movie):
    kept = RememberedBookmarks(
        {file_key(movie): RememberedFile(uri=movie, bookmarks=A, fingerprint="1:ab")}
    )

    again = RememberedBookmarks.model_validate_json(kept.model_dump_json())

    assert again == kept


def test_those_kept_before_fingerprints_read_back(movie):
    """As the settings of a player before files were told by what is in
    them have them: no fingerprint, found by the path alone."""

    kept = json.dumps(
        {
            file_key(movie): {
                "uri": movie.as_posix(),
                "cell": None,
                "bookmarks": [{"time_ms": 10000}],
            }
        }
    )

    read = RememberedBookmarks.model_validate_json(kept)

    assert read.root[file_key(movie)].fingerprint is None
    assert read.root[file_key(movie)].bookmarks == [Bookmark(time_ms=10000)]
