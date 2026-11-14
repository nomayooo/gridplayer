"""The loops last left on a file, kept with the settings and taken up again
by a cell that opens the file with none of its own.

A real block, on a stand-in frame that plays nothing and goes wherever it
is sent.
"""

from PyQt5.QtWidgets import QWidget

from gridplayer.models.remembered_loops import MAX_FILES, FileLoops, RememberedLoops
from gridplayer.models.video import Video
from gridplayer.params.static import VideoEndAction, VideoInitialState
from gridplayer.settings import Settings
from gridplayer.utils.bookmarks import file_key
from gridplayer.widgets.video_block import VideoBlock
from tests import test_video_block_chapters as chapter_tests
from tests.test_video_block_loops import _make_loop

# the real block the chapter tests play with, and the settings kept apart
block = chapter_tests.block
_isolated_settings = chapter_tests._isolated_settings


def _remembered(uri) -> FileLoops | None:
    return Settings().get("loops/remembered").get(file_key(uri))


def _open(tmp_path, uri, **fields):
    """Another cell opening a file, as the block fixture opens its own."""

    parent = QWidget()

    other = VideoBlock(
        video_driver=chapter_tests._ChapterFrame,
        context=chapter_tests._context(),
        parent=parent,
    )
    other._test_parent = parent

    other.set_video(
        Video(
            uri=uri,
            playback_state=VideoInitialState.PAUSED,
            end_action=VideoEndAction.LOOP_FILE,
            **fields,
        )
    )

    return other


def _close(other):
    other.cleanup()
    other.url_resolver.cleanup()


class TestTheStore:
    def test_nothing_left_forgets_the_file(self):
        remembered = RememberedLoops()
        remembered.put("a", FileLoops(loops=[(1, 2)]))
        remembered.put("a", FileLoops())

        assert remembered.get("a") is None

    def test_a_loop_begun_is_kept_too(self):
        remembered = RememberedLoops()
        remembered.put("a", FileLoops(loop_start=500))

        assert remembered.get("a") == FileLoops(loop_start=500)

    def test_the_files_looped_longest_ago_are_let_go(self):
        remembered = RememberedLoops()

        for index in range(MAX_FILES + 1):
            remembered.put(str(index), FileLoops(loops=[(1, 2)]))

        # the first looped again is the last now, and stays
        remembered.put("1", FileLoops(loops=[(3, 4)]))
        remembered.put("extra", FileLoops(loops=[(1, 2)]))

        assert len(remembered.files) == MAX_FILES
        assert remembered.get("0") is None
        assert remembered.get("2") is None
        assert remembered.get("1") == FileLoops(loops=[(3, 4)])

    def test_kept_as_the_settings_keep_it(self):
        remembered = RememberedLoops()
        remembered.put("a", FileLoops(loops=[(1, None)], loop_start=7))

        Settings().set("loops/remembered", remembered)

        assert Settings().get("loops/remembered") == remembered


class TestRemembering:
    def test_a_loop_made_is_remembered_for_the_file(self, block):
        _make_loop(block, 5000, 8000)

        assert _remembered(block.video_params.uri) == FileLoops(loops=[(5000, 8000)])

    def test_a_loop_begun_is_remembered(self, block):
        block.seek(5000)
        block.loop.set_start()

        assert _remembered(block.video_params.uri) == FileLoops(loop_start=5000)

    def test_taking_one_back_is_remembered(self, block):
        _make_loop(block, 5000, 8000)
        _make_loop(block, 20000, 30000)

        block.loop.remove_last()

        assert _remembered(block.video_params.uri).loops == [(5000, 8000)]

    def test_resetting_them_forgets_the_file(self, block):
        _make_loop(block, 5000, 8000)

        block.loop.reset()

        assert _remembered(block.video_params.uri) is None

    def test_stopping_the_video_does_not_forget_them(self, block):
        _make_loop(block, 5000, 8000)

        block.loop.clear()

        assert _remembered(block.video_params.uri).loops == [(5000, 8000)]


class TestOpeningAgain:
    def test_another_cell_opening_the_file_has_its_loops(self, block, tmp_path):
        _make_loop(block, 20000, 30000)
        _make_loop(block, 5000, 8000)

        other = _open(tmp_path, block.video_params.uri)

        try:
            assert other.video_params.loops == [(20000, 30000), (5000, 8000)]
            assert other.video_params.loop_index == 0
        finally:
            _close(other)

    def test_a_file_with_none_remembered_opens_without(self, block, tmp_path):
        _make_loop(block, 5000, 8000)

        another_file = tmp_path / "another.mkv"
        another_file.touch()

        other = _open(tmp_path, another_file)

        try:
            assert other.video_params.loops == []
            assert other.video_params.loop_start is None
        finally:
            _close(other)

    def test_one_opened_with_loops_of_its_own_keeps_them(self, block, tmp_path):
        """A favourite, or a playlist saved with them."""

        _make_loop(block, 5000, 8000)

        other = _open(tmp_path, block.video_params.uri, loops=[(1000, 2000)])

        try:
            assert other.video_params.loops == [(1000, 2000)]
        finally:
            _close(other)

    def test_going_on_to_another_file_and_back(self, block, tmp_path):
        first = block.video_params.uri
        _make_loop(block, 5000, 8000)

        another_file = tmp_path / "another.mkv"
        another_file.touch()

        block.navigation.switch_to(another_file)

        assert block.video_params.loops == []
        # the file left keeps its loops
        assert _remembered(first).loops == [(5000, 8000)]

        _make_loop(block, 20000, 30000)

        block.navigation.switch_to(first)

        assert block.video_params.loops == [(5000, 8000)]
        assert _remembered(another_file).loops == [(20000, 30000)]
