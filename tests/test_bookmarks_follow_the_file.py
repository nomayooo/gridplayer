"""Remembered bookmarks following a file by what is in it: found again when
it is moved or renamed, those kept before still found by its path, and a
file changed where it is found by its path too."""

from types import SimpleNamespace
from uuid import uuid4

import pytest
from PyQt5.QtWidgets import QWidget

from gridplayer.models.bookmark import Bookmark
from gridplayer.models.file_bookmarks import RememberedBookmarks, RememberedFile
from gridplayer.player.managers.bookmarks import BookmarksManager
from gridplayer.utils import file_fingerprint as fingerprint_module
from gridplayer.utils.bookmarks import file_key
from gridplayer.utils.file_fingerprint import PIECE_SIZE, file_fingerprint

A = [Bookmark(time_ms=10000), Bookmark(time_ms=30000, name="Goal")]


@pytest.fixture(autouse=True)
def _forget_fingerprints(monkeypatch):
    monkeypatch.setattr(fingerprint_module, "_known", {})


def _file(path, content=b"one film" * 1000):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return path


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


def _bookmarked(manager, path):
    """Bookmarks made on the file, then the playlist gone, as on closing."""

    manager.registry.set(path, None, A)
    manager.registry.clear()


def _opened(manager, path):
    manager.registry.claim(path, uuid4())
    return list(manager.registry.get(path, None))


class TestMoved:
    def test_found_where_it_was_moved_to(self, manager, tmp_path, remembered_bookmarks):
        film = _file(tmp_path / "films" / "film.mkv")
        _bookmarked(manager, film)

        moved = tmp_path / "elsewhere" / "film.mkv"
        moved.parent.mkdir()
        film.rename(moved)

        assert _opened(manager, moved) == A

    def test_found_renamed(self, manager, tmp_path, remembered_bookmarks):
        film = _file(tmp_path / "film.mkv")
        _bookmarked(manager, film)

        renamed = film.rename(tmp_path / "Better name.mkv")

        assert _opened(manager, renamed) == A

    def test_kept_where_it_is_now_none_left_where_it_was(
        self, manager, tmp_path, remembered_bookmarks
    ):
        film = _file(tmp_path / "film.mkv")
        _bookmarked(manager, film)
        renamed = film.rename(tmp_path / "renamed.mkv")

        _opened(manager, renamed)

        assert list(_remembered(remembered_bookmarks)) == [file_key(renamed)]
        assert _remembered(remembered_bookmarks)[file_key(renamed)].uri == renamed

    def test_another_file_put_where_it_was_has_none(
        self, manager, tmp_path, remembered_bookmarks
    ):
        film = _file(tmp_path / "film.mkv")
        _bookmarked(manager, film)
        renamed = film.rename(tmp_path / "renamed.mkv")
        _opened(manager, renamed)
        manager.registry.clear()

        _file(film, b"another film" * 1000)

        assert _opened(manager, film) == []

    def test_changed_after_it_is_moved_kept_where_it_is(
        self, manager, tmp_path, remembered_bookmarks
    ):
        film = _file(tmp_path / "film.mkv")
        _bookmarked(manager, film)
        renamed = film.rename(tmp_path / "renamed.mkv")
        _opened(manager, renamed)

        manager.registry.set(renamed, None, A[:1])

        kept = _remembered(remembered_bookmarks)
        assert list(kept) == [file_key(renamed)]
        assert kept[file_key(renamed)].bookmarks == A[:1]

    def test_all_taken_away_once_moved_none_left_anywhere(
        self, manager, tmp_path, remembered_bookmarks
    ):
        film = _file(tmp_path / "film.mkv")
        _bookmarked(manager, film)
        renamed = film.rename(tmp_path / "renamed.mkv")
        _opened(manager, renamed)

        manager.registry.set(renamed, None, [])

        assert _remembered(remembered_bookmarks) == {}

    def test_copies_alike_share_them(self, manager, tmp_path, remembered_bookmarks):
        film = _file(tmp_path / "film.mkv")
        _bookmarked(manager, film)

        copy = _file(tmp_path / "copy.mkv")

        assert _opened(manager, copy) == A


class TestKeptBefore:
    """Remembered before files were told by what is in them: by the path
    alone."""

    @pytest.fixture
    def kept_before(self, tmp_path, remembered_bookmarks):
        film = _file(tmp_path / "film.mkv")
        remembered_bookmarks.set(
            "bookmarks/remembered",
            RememberedBookmarks(
                {file_key(film): RememberedFile(uri=film, bookmarks=A)}
            ),
        )
        return film

    def test_still_found_by_its_path(self, manager, kept_before):
        assert _opened(manager, kept_before) == A

    def test_told_by_what_is_in_it_once_found(
        self, manager, kept_before, remembered_bookmarks
    ):
        _opened(manager, kept_before)

        kept = _remembered(remembered_bookmarks)[file_key(kept_before)]
        assert kept.fingerprint == file_fingerprint(kept_before)

    def test_then_followed_when_moved(self, manager, kept_before, tmp_path):
        _opened(manager, kept_before)
        manager.registry.clear()

        moved = kept_before.rename(tmp_path / "moved.mkv")

        assert _opened(manager, moved) == A

    def test_one_moved_before_it_was_found_again_is_not(
        self, manager, kept_before, tmp_path
    ):
        moved = kept_before.rename(tmp_path / "moved.mkv")

        assert _opened(manager, moved) == []

    def test_a_link_by_its_address(self, manager, remembered_bookmarks):
        link = "https://example.com/live.m3u8"
        remembered_bookmarks.set(
            "bookmarks/remembered",
            RememberedBookmarks({link: RememberedFile(uri=link, bookmarks=A)}),
        )

        assert _opened(manager, link) == A
        assert _remembered(remembered_bookmarks)[link].fingerprint is None


class TestChangedWhereItIs:
    def test_found_by_its_path(self, manager, tmp_path):
        film = _file(tmp_path / "film.mkv")
        _bookmarked(manager, film)

        _file(film, b"re-encoded" * 1000)

        assert _opened(manager, film) == A

    def test_changed_and_moved_lost(self, manager, tmp_path):
        film = _file(tmp_path / "film.mkv")
        _bookmarked(manager, film)

        film.unlink()
        moved = _file(tmp_path / "moved.mkv", b"re-encoded" * 1000)

        assert _opened(manager, moved) == []


class TestTheFingerprint:
    def test_the_same_wherever_it_is(self, tmp_path):
        one = _file(tmp_path / "a" / "film.mkv")
        other = _file(tmp_path / "b" / "other name.mkv")

        assert file_fingerprint(one) == file_fingerprint(other) is not None

    def test_another_for_what_is_in_it_changed(self, tmp_path):
        one = _file(tmp_path / "one.mkv")
        before = file_fingerprint(one)

        _file(one, b"something else" * 1000)

        assert file_fingerprint(one) != before

    def test_another_for_a_size_changed(self, tmp_path):
        one = _file(tmp_path / "one.mkv", b"x" * 100)
        other = _file(tmp_path / "other.mkv", b"x" * 101)

        assert file_fingerprint(one) != file_fingerprint(other)

    def test_its_end_counts(self, tmp_path):
        size = PIECE_SIZE * 4
        one = _file(tmp_path / "one.mkv", b"\0" * size)
        other = _file(tmp_path / "other.mkv", b"\0" * (size - 1) + b"\1")

        assert file_fingerprint(one) != file_fingerprint(other)

    def test_only_its_ends_read(self, tmp_path, monkeypatch):
        """However big: a piece of its start and one of its end."""

        size = PIECE_SIZE * 100
        film = _file(tmp_path / "big.mkv", b"\0" * size)
        read = []
        real_open = type(film).open

        def counting_open(self, *args, **kwargs):
            file = real_open(self, *args, **kwargs)
            real_read = file.read

            def counted(n=-1):
                data = real_read(n)
                read.append(len(data))
                return data

            file.read = counted
            return file

        monkeypatch.setattr(type(film), "open", counting_open)

        file_fingerprint(film)

        assert sum(read) == 2 * PIECE_SIZE

    def test_read_once(self, tmp_path, monkeypatch):
        film = _file(tmp_path / "film.mkv")
        reads = []
        real = fingerprint_module._read
        monkeypatch.setattr(
            fingerprint_module,
            "_read",
            lambda path, size: reads.append(path) or real(path, size),
        )

        file_fingerprint(film)
        file_fingerprint(film)

        assert len(reads) == 1

    def test_none_for_what_is_not_there_or_a_link(self, tmp_path):
        assert file_fingerprint(tmp_path / "gone.mkv") is None
        assert file_fingerprint(tmp_path) is None
        assert file_fingerprint("https://example.com/a.mp4") is None

    def test_a_small_one_whole(self, tmp_path):
        assert file_fingerprint(_file(tmp_path / "tiny.mkv", b"abc")).startswith("3:")
