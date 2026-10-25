"""The loops of a video block: the stretches of it played over and over, one
after another in the order they were made and round again, and whether each
pass starts somewhere at random.

A loop is made in two steps. Set Loop Start begins one where the video is,
and until it is finished the video plays from there to the end of the file
and round, the loops made before it waiting; a seek may go anywhere, before
it too, so that it can be put wherever it is wanted, Set Loop Start again
moving it there. Set Loop End finishes it where the video is then, and it
joins the others, playing; without one begun, Set Loop End does nothing.
A-B Loop is both on one key: it begins one without one begun, and finishes
the one begun otherwise. Undo Loop Marker takes them back a step at a
time: the end of the last loop made, leaving it begun from its start, or
the start of the one begun.

Where a loop ends up taking the video is the block's (see loop_start,
loop_end and time_changed); here is only how the viewer sets them.
"""

from gridplayer.models.video import LoopSpan
from gridplayer.widgets.video_block_guards import VideoBlockPart, only_seekable


class LoopControl(VideoBlockPart):
    @property
    def _params(self):
        return self._block.video_params

    @only_seekable
    def toggle_random(self):
        self.set_random(not self._block.video_params.is_start_random)

    def set_random(self, is_start_random: bool):
        """Start each pass somewhere at random, or where the loop starts.

        Kept for a video stopped or still loading too, which goes by it
        once it plays, and for one that is live, which never loops.
        """

        self._block.video_params.is_start_random = is_start_random

    # making them

    @only_seekable
    def set_start(self):
        self.set_start_time(self._block.time)

    @only_seekable
    def set_start_time(self, new_time: int):
        """Begin a loop here, or move the start of the one begun."""

        if new_time is None:
            return

        self._params.loop_start = new_time

        self.announce()

    @only_seekable
    def set_end(self):
        self.set_end_time(self._block.time)

    @only_seekable
    def set_end_time(self, new_time: int):
        """Finish the loop begun here, and play it; nothing without one, or
        here being no later than it starts."""

        start = self._params.loop_start

        if start is None or new_time is None or new_time <= start:
            return

        self._add((start, new_time))

    @only_seekable
    def set_start_or_end(self):
        """Begin a loop here without one begun, else finish the one begun
        here; here being no later than it starts, it is begun here again."""

        start = self._params.loop_start
        time = self._block.time

        if start is None or time is None or time <= start:
            self.set_start_time(time)
        else:
            self.set_end_time(time)

    def replace_with(self, span: LoopSpan):
        """This one loop in place of any there were."""

        self._params.loops = []
        self._add(span)

    def _add(self, span: LoopSpan):
        self._params.loops.append(span)
        self._params.loop_index = len(self._params.loops) - 1
        self._params.loop_start = None
        self._params.is_outside_loops = False

        self.announce()

    # taking them away

    @only_seekable
    def reset(self):
        self.clear()

    def clear(self):
        """No loops, finished or begun: the whole video plays."""

        self._params.loops = []
        self._params.loop_index = 0
        self._params.loop_start = None
        self._params.is_outside_loops = False

        self.announce()

    @only_seekable
    def remove_last(self):
        """Take back the loop begun, or else the last one made."""

        params = self._params

        if params.loop_start is not None:
            params.loop_start = None
        elif params.loops:
            params.loops.pop()
            if params.loop_index >= len(params.loops):
                params.loop_index = 0
        else:
            return

        self.announce()

    @only_seekable
    def undo_marker(self):
        """Take back the last marker set: the start of the loop begun, or
        else the end of the last one made, which is begun again from its
        start, for another end to be set."""

        params = self._params

        if params.loop_start is not None:
            params.loop_start = None
        elif params.loops:
            start, _ = params.loops.pop()
            params.loop_start = start
            params.is_outside_loops = False
            if params.loop_index >= len(params.loops):
                params.loop_index = 0
        else:
            return

        self.announce()

    # going from one to another

    @only_seekable
    def next(self):
        self._go(1)

    @only_seekable
    def previous(self):
        self._go(-1)

    def _go(self, step: int):
        # from outside them, back to the one it left
        if self._params.is_outside_loops and not self._params.is_loop_open:
            self.rejoin()
        elif not self.step(step):
            return

        self._block._loop_to_start()

    def rejoin(self):
        """Back to the loop playing, from outside every one."""

        self._params.is_outside_loops = False

        self.announce()

    def step(self, step: int) -> bool:
        """Make the loop that many on from the one playing, round the end of
        them, the one playing; whether there was another to go to. None while
        one is being made, which is the only one playing then."""

        params = self._params

        if params.loop_start is not None or len(params.loops) < 2:
            return False

        params.loop_index = (params.loop_index + step) % len(params.loops)

        self.announce()

        return True

    def adopt_at(self, time_ms: int):
        """Play the loop a time is in, the one playing if it has it, else the
        next one round that does; outside every one, play the video as it is
        from there. Where a viewer's seek landed, or where the video got to
        while outside them."""

        params = self._params

        if params.loop_start is not None or not params.loops:
            return

        count = len(params.loops)
        for offset in range(count):
            index = (params.loop_index + offset) % count
            if self._is_in(params.loops[index], time_ms):
                if index != params.loop_index or params.is_outside_loops:
                    params.loop_index = index
                    params.is_outside_loops = False
                    self.announce()
                return

        if not params.is_outside_loops:
            params.is_outside_loops = True
            self.announce()

    def _is_in(self, span: LoopSpan, time_ms: int) -> bool:
        start, end = span
        if end is None:
            end = self._length()

        return start <= time_ms <= end

    # showing them

    def announce(self):
        """Tell the overlay where the loops are: the one playing, and the
        rest apart from it."""

        block = self._block
        params = self._params

        current = params.current_loop

        if current is None:
            block.loop_start_change.emit(0)
            block.loop_end_change.emit(100.0)
        else:
            start, end = current
            block.loop_start_change.emit(self._fraction(start))
            block.loop_end_change.emit(100.0 if end is None else self._fraction(end))

        others = tuple(
            (self._fraction(start), 1.0 if end is None else self._fraction(end))
            for index, (start, end) in enumerate(params.loops)
            if params.loop_start is not None
            or params.is_outside_loops
            or index != params.loop_index
        )

        block.loops_change.emit(others)

    def _fraction(self, time_ms: int) -> float:
        length = self._length()

        if not length:
            return 0

        return time_ms / length

    def _length(self) -> int:
        driver = self._block.video_driver

        if driver is None or not driver.length:
            return 0

        return driver.length
