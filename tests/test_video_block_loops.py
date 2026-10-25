"""Several loops on a video block: made one after another, played in the
order they were made and round again.

A real block, on a stand-in frame that plays nothing and goes wherever it
is sent.
"""

import pytest

from gridplayer.models.video import Video
from tests import test_video_block_chapters as chapter_tests

LENGTH = chapter_tests.LENGTH
_reported = chapter_tests._reported

# the real block the chapter tests play with, and the settings kept apart
block = chapter_tests.block
_isolated_settings = chapter_tests._isolated_settings


def _make_loop(block, start_ms, end_ms):
    """As a viewer would: begin one here, go there, finish it."""

    block.loop.set_start()
    block.seek(start_ms)
    block.loop.set_start()
    block.seek(end_ms)
    block.loop.set_end()


@pytest.fixture
def two_loops(block):
    _make_loop(block, 20000, 30000)
    _make_loop(block, 5000, 8000)

    assert block.video_params.loops == [(20000, 30000), (5000, 8000)]

    return block


class TestMakingThem:
    def test_set_loop_end_finishes_the_loop_begun_and_plays_it(self, block):
        block.seek(5000)
        block.loop.set_start()
        block.seek(8000)
        block.loop.set_end()

        assert block.video_params.loops == [(5000, 8000)]
        assert block.video_params.loop_start is None
        assert (block.loop_start, block.loop_end) == (5000, 8000)

    def test_set_loop_end_with_none_begun_does_nothing(self, block):
        block.seek(8000)
        block.loop.set_end()

        assert block.video_params.loops == []
        assert block.video_params.current_loop is None

    def test_an_end_no_later_than_the_start_is_refused(self, block):
        block.seek(8000)
        block.loop.set_start()
        block.seek(8000)
        block.loop.set_end()

        assert block.video_params.loops == []
        assert block.video_params.loop_start == 8000

    def test_set_loop_start_again_moves_the_start_of_the_one_begun(self, block):
        block.seek(5000)
        block.loop.set_start()
        block.seek(9000)
        block.loop.set_start()

        assert block.video_params.loop_start == 9000

    def test_the_loop_begun_lets_the_video_go_back_before_it(self, two_loops):
        """So that the next loop can be put anywhere, before the others too."""

        two_loops.loop.set_start()
        two_loops.seek(1000)

        assert two_loops.time == 1000

    def test_loops_may_overlap(self, block):
        _make_loop(block, 5000, 9000)
        _make_loop(block, 7000, 12000)

        assert block.video_params.loops == [(5000, 9000), (7000, 12000)]


class TestOneKeyForBoth:
    def test_begins_one_then_finishes_it(self, block):
        block.seek(5000)
        block.loop.set_start_or_end()

        assert block.video_params.loop_start == 5000
        assert block.video_params.loops == []

        block.seek(8000)
        block.loop.set_start_or_end()

        assert block.video_params.loops == [(5000, 8000)]
        assert block.video_params.loop_start is None

    def test_after_one_made_begins_another(self, block):
        _make_loop(block, 5000, 8000)

        block.seek(20000)
        block.loop.set_start_or_end()

        assert block.video_params.loop_start == 20000
        assert block.video_params.loops == [(5000, 8000)]

    def test_back_before_the_start_begins_it_there_instead(self, block):
        block.seek(9000)
        block.loop.set_start_or_end()
        block.seek(4000)
        block.loop.set_start_or_end()

        assert block.video_params.loop_start == 4000
        assert block.video_params.loops == []


class TestUndoingAMarker:
    def test_the_start_of_the_one_begun(self, block):
        block.seek(5000)
        block.loop.set_start()

        block.loop.undo_marker()

        assert block.video_params.loop_start is None
        assert block.video_params.loops == []

    def test_the_end_of_the_last_made_leaving_it_begun(self, two_loops):
        two_loops.loop.undo_marker()

        assert two_loops.video_params.loops == [(20000, 30000)]
        assert two_loops.video_params.loop_start == 5000

    def test_a_new_end_set_after(self, block):
        _make_loop(block, 5000, 8000)
        block.loop.undo_marker()

        block.seek(12000)
        block.loop.set_end()

        assert block.video_params.loops == [(5000, 12000)]

    def test_a_marker_at_a_time_back_to_none(self, two_loops):
        # the second's end and start, then the first's end
        for _ in range(3):
            two_loops.loop.undo_marker()

        assert two_loops.video_params.loops == []
        assert two_loops.video_params.loop_start == 20000

        two_loops.loop.undo_marker()
        assert two_loops.video_params.loop_start is None

        # nothing left: nothing done
        two_loops.loop.undo_marker()
        assert two_loops.video_params.loops == []

    def test_one_key_for_both_goes_on_from_there(self, block):
        _make_loop(block, 5000, 8000)
        block.loop.undo_marker()

        block.seek(9000)
        block.loop.set_start_or_end()

        assert block.video_params.loops == [(5000, 9000)]


class TestPlayingThem:
    def test_the_end_of_one_goes_on_to_the_next_round_to_the_first(self, two_loops):
        # the last made is playing, the end of which goes round to the first
        _reported(two_loops, 8200)
        assert two_loops.time == 20000
        assert two_loops.video_params.loop_index == 0

        _reported(two_loops, 30200)
        assert two_loops.time == 5000
        assert two_loops.video_params.loop_index == 1

    def test_one_loop_plays_over_and_over_as_ever(self, block):
        _make_loop(block, 5000, 8000)

        _reported(block, 8200)

        assert block.time == 5000

    def test_seeking_into_another_loop_plays_that_one(self, two_loops):
        two_loops.seek(25000)

        assert two_loops.time == 25000
        assert two_loops.video_params.loop_index == 0

    def test_wheeling_past_the_end_of_one_goes_on_to_the_next(self, two_loops):
        two_loops.seek(7900)

        two_loops.seek_shift_ms(500)

        assert two_loops.time == 20000

    def test_wheeling_back_past_the_start_of_one_goes_into_the_one_before(
        self, two_loops
    ):
        two_loops.seek(5100)

        two_loops.seek_shift_ms(-600)

        assert two_loops.video_params.loop_index == 0
        assert two_loops.time == 29500

    def test_next_and_previous_go_from_one_to_another(self, two_loops):
        two_loops.loop.next()
        assert (two_loops.video_params.loop_index, two_loops.time) == (0, 20000)

        two_loops.loop.previous()
        assert (two_loops.video_params.loop_index, two_loops.time) == (1, 5000)


class TestOutsideThem:
    """A viewer's seek outside every loop plays the video as it is from
    there, so that a next loop can be made anywhere."""

    def test_seeking_outside_any_loop_goes_there(self, two_loops):
        two_loops.seek(50000)

        assert two_loops.time == 50000
        assert two_loops.video_params.is_outside_loops
        assert two_loops.video_params.current_loop is None

    def test_one_loop_lets_the_video_out_too(self, block):
        _make_loop(block, 5000, 8000)

        block.seek(50000)
        _reported(block, 50200)

        assert block.time == 50200

    def test_it_plays_on_without_being_taken_back(self, two_loops):
        two_loops.seek(40000)

        _reported(two_loops, 45000)

        assert two_loops.time == 45000
        assert two_loops.video_params.is_outside_loops

    def test_playing_into_a_loop_plays_that_one(self, two_loops):
        two_loops.seek(15000)

        _reported(two_loops, 20100)

        assert not two_loops.video_params.is_outside_loops
        assert two_loops.video_params.loop_index == 0

        _reported(two_loops, 30200)
        assert two_loops.time == 5000

    def test_seeking_into_a_loop_plays_it_as_a_loop(self, two_loops):
        two_loops.seek(50000)

        two_loops.seek(6000)

        assert not two_loops.video_params.is_outside_loops
        assert two_loops.video_params.loop_index == 1

        # its end goes on to the next, as ever
        _reported(two_loops, 8200)
        assert (two_loops.video_params.loop_index, two_loops.time) == (0, 20000)

    def test_the_end_of_the_file_goes_back_to_the_loop_left(self, two_loops):
        two_loops.seek(50000)

        two_loops.loop_end_action()

        assert not two_loops.video_params.is_outside_loops
        assert two_loops.video_params.loop_index == 1
        assert two_loops.time == 5000

    def test_wheeling_past_the_end_of_the_file_goes_back_too(self, two_loops):
        two_loops.seek(LENGTH - 500)

        two_loops.seek_shift_ms(1000)

        assert two_loops.video_params.loop_index == 1
        assert two_loops.time == 5000

    def test_next_goes_back_to_the_loop_left(self, block):
        _make_loop(block, 5000, 8000)
        block.seek(50000)

        block.loop.next()

        assert not block.video_params.is_outside_loops
        assert block.time == 5000

    def test_a_loop_made_out_there_is_one_more(self, two_loops):
        two_loops.seek(40000)
        two_loops.loop.set_start()
        two_loops.seek(45000)
        two_loops.loop.set_end()

        params = two_loops.video_params
        assert params.loops == [(20000, 30000), (5000, 8000), (40000, 45000)]
        assert not params.is_outside_loops
        assert (two_loops.loop_start, two_loops.loop_end) == (40000, 45000)

    def test_the_bar_shows_every_loop_apart(self, two_loops):
        two_loops.seek(50000)

        assert len(two_loops.overlay.progress_bar.other_loops) == 2

    def test_reset_leaves_it_outside_nothing(self, two_loops):
        two_loops.seek(50000)

        two_loops.loop.reset()

        assert not two_loops.video_params.is_outside_loops


class TestTakingThemAway:
    def test_remove_last_takes_back_the_last_made(self, two_loops):
        two_loops.loop.remove_last()

        assert two_loops.video_params.loops == [(20000, 30000)]
        assert two_loops.video_params.loop_index == 0

    def test_remove_last_takes_back_the_one_begun_first(self, two_loops):
        two_loops.loop.set_start()

        two_loops.loop.remove_last()

        assert two_loops.video_params.loop_start is None
        assert len(two_loops.video_params.loops) == 2

    def test_loop_reset_takes_them_all(self, two_loops):
        two_loops.loop.set_start()

        two_loops.loop.reset()

        assert two_loops.video_params.current_loop is None
        assert two_loops.video_params.loops == []


class TestTheBar:
    def test_the_one_playing_is_marked_and_the_rest_apart(self, two_loops):
        bar = two_loops.overlay.progress_bar

        assert (bar.loop_start, bar.loop_end) == (5000 / LENGTH, 8000 / LENGTH)
        assert bar.other_loops == ((20000 / LENGTH, 30000 / LENGTH),)

    def test_while_one_is_begun_all_the_made_ones_are_apart(self, two_loops):
        two_loops.loop.set_start()

        assert len(two_loops.overlay.progress_bar.other_loops) == 2


class TestSaving:
    def test_one_loop_saved_before_there_could_be_several_is_one_of_them(self):
        video = Video(uri="http://example.com/a.mp4", loop_start=1000, loop_end=5000)

        assert video.loops == [(1000, 5000)]
        assert video.loop_start is None

    def test_an_end_alone_loops_from_the_start(self):
        video = Video(uri="http://example.com/a.mp4", loop_end=5000)

        assert video.loops == [(0, 5000)]

    def test_a_start_alone_is_still_a_loop_begun(self):
        video = Video(uri="http://example.com/a.mp4", loop_start=1000)

        assert video.loops == []
        assert video.loop_start == 1000

    def test_the_loops_come_back_as_they_were(self):
        video = Video(
            uri="http://example.com/a.mp4",
            loops=[(20000, 30000), (5000, None)],
            loop_index=1,
        )

        again = Video.model_validate(video.model_dump(mode="json"))

        assert again.loops == [(20000, 30000), (5000, None)]
        assert again.loop_index == 1
