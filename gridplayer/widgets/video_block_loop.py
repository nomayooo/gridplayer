"""The loops of a video block: the stretches of it played over and over, one
after another in the order they were made and round again, and whether each
pass starts somewhere at random.

A loop is made in two steps. Set Loop Start begins one where the video is,
and until it is finished the video plays from there to the end of the file
and round, the loops made before it waiting; a seek may go anywhere, before
it too. Set Loop Start again begins another there, the one before it kept
begun too, waiting. Set Loop End finishes the one begun last where the
video is then, and it joins the others; the one begun before it, if any,
is then the one begun, playing, for the next end. Without one begun, Set
Loop End does nothing. A-B Loop is both on one key: it finishes the one
begun last where the video is past its start, and begins another
otherwise. Undo Loop Marker takes them back a step at a time: the start
of the one begun last, or else the end of the last loop made, leaving it
begun from its start.

Next and Previous Loop go from one loop made to another, in the order they
were made and round again; with only one, back to its start. With a loop
begun, the video free to go anywhere, they go from one start marker to the
next or the one before on the bar, the begun one's too, and round again.

Where a loop ends up taking the video is the block's (see loop_start,
loop_end and time_changed); here is only how the viewer sets them.
"""

from gridplayer.models.video import LoopSpan
from gridplayer.widgets.video_block_guards import VideoBlockPart, only_seekable
from gridplayer.widgets.video_overlay_elements import loop_color

# a marker the video is at, or just past, is the one it is at: the next is
# the one after it, the one before the one before it
START_MARKER_MARGIN_MS = 500


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
        """Begin a loop here, any begun before it kept begun, waiting."""

        if new_time is None:
            return

        params = self._params

        if params.loop_start == new_time:
            return

        if params.loop_start is not None:
            params.earlier_loop_starts.append(params.loop_start)

        params.loop_start = new_time

        self.announce()

    @only_seekable
    def set_end(self):
        self.set_end_time(self._block.time)

    @only_seekable
    def set_end_time(self, new_time: int):
        """Finish the loop begun last here; nothing without one, or here
        being no later than it starts. Without another begun, it plays."""

        start = self._params.loop_start

        if start is None or new_time is None or new_time <= start:
            return

        self._add((start, new_time))

    @only_seekable
    def set_start_or_end(self):
        """Finish the loop begun last here, here being past its start; else
        begin another here."""

        start = self._params.loop_start
        time = self._block.time

        if start is None or time is None or time <= start:
            self.set_start_time(time)
        else:
            self.set_end_time(time)

    def replace_with(self, span: LoopSpan):
        """This one loop in place of any there were, finished or begun."""

        self._params.loops = []
        self._params.loop_start = None
        self._params.earlier_loop_starts = []
        self._add(span)

    def _add(self, span: LoopSpan):
        params = self._params

        params.loops.append(span)
        params.loop_index = len(params.loops) - 1
        # the one begun before it begun again, if any
        params.loop_start = self._take_earlier_start()
        params.is_outside_loops = False

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
        self._params.earlier_loop_starts = []
        self._params.is_outside_loops = False

        self.announce()

    @only_seekable
    def remove_last(self):
        """Take back the loop begun last, or else the last one made."""

        params = self._params

        if params.loop_start is not None:
            params.loop_start = self._take_earlier_start()
        elif params.loops:
            params.loops.pop()
            if params.loop_index >= len(params.loops):
                params.loop_index = 0
        else:
            return

        self.announce()

    @only_seekable
    def undo_marker(self):
        """Take back the last marker set: the start of the loop begun last,
        the one begun before it begun again, or else the end of the last one
        made, which is begun again from its start, for another end to be
        set."""

        params = self._params

        if params.loop_start is not None:
            params.loop_start = self._take_earlier_start()
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
        params = self._params

        if params.loop_start is not None:
            self._to_start_marker(step)
            return

        # from outside them, back to the one it left
        if params.is_outside_loops and not params.is_loop_open:
            self.rejoin()
        elif len(params.loops) == 1:
            # the one there is, from its start again
            pass
        elif not self.step(step):
            return

        self._block._loop_to_start()

    def _to_start_marker(self, step: int):
        """With a loop begun: to the next start marker on the bar after
        where the video is, or the one before, round the ends of them."""

        params = self._params
        starts = sorted(
            {start for start, _ in params.loops}
            | {params.loop_start, *params.earlier_loop_starts}
        )

        now = self._block.time or 0

        if step > 0:
            later = [s for s in starts if s > now + START_MARKER_MARGIN_MS]
            target = later[0] if later else starts[0]
        else:
            earlier = [s for s in starts if s < now - START_MARKER_MARGIN_MS]
            target = earlier[-1] if earlier else starts[-1]

        self._block.seek(target)

    def _take_earlier_start(self) -> int | None:
        earlier = self._params.earlier_loop_starts
        return earlier.pop() if earlier else None

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
        """Tell the overlay where the loops are, each in its own colour: the
        one playing, and the rest apart from it."""

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

        block.loop_color_change.emit(self._current_color())

        others = tuple(
            (
                self._fraction(start),
                1.0 if end is None else self._fraction(end),
                loop_color(index),
            )
            for index, (start, end) in enumerate(params.loops)
            if params.loop_start is not None
            or params.is_outside_loops
            or index != params.loop_index
        )

        # the starts of those begun before the one begun last, waiting
        waiting = tuple(
            (self._fraction(start), 1.0, loop_color(index))
            for index, start in self._waiting_starts()
        )

        block.loops_change.emit(others + waiting)

    def _current_color(self) -> str:
        params = self._params

        if params.loop_start is not None:
            return loop_color(len(params.loops))

        return loop_color(params.loop_index)

    def _waiting_starts(self) -> list[tuple[int, int]]:
        """Those begun before the one begun last, each with the place it
        will have among the loops: the one begun last finished first, the
        one begun before it next, and so on, so that each keeps its colour
        from its start to its end."""

        params = self._params
        after_last = len(params.loops) + 1

        return [
            (after_last + offset, start)
            for offset, start in enumerate(reversed(params.earlier_loop_starts))
        ]

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
