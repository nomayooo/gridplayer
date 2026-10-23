"""The picture at the time under the mouse on the seek bar: asked of the seek
previewer (see gridplayer.utils.seek_preview) for the file the cell plays, and
given to the overlay's hover label as it comes.

Of files on disk only, and not while the setting is off.
"""

import weakref

from PyQt5 import sip

from gridplayer.settings import Settings
from gridplayer.widgets.video_block_guards import (
    VideoBlockPart,
    only_initialized,
    only_local_file,
    only_seekable,
    only_with_video_tacks,
)


class PreviewControl(VideoBlockPart):
    @only_initialized
    @only_seekable
    @only_local_file
    @only_with_video_tacks
    def warm_up(self):
        """A video to preview loaded: the previewer started now, for the
        first picture not to wait for it to start."""

        previewer = self._previewer()

        if previewer is not None:
            previewer.warm_up()

    @only_initialized
    @only_seekable
    @only_local_file
    @only_with_video_tacks
    def want(self, time_ms: int):
        previewer = self._previewer()
        if previewer is None:
            return

        path = self._block.video_params.uri

        if not previewer.is_readable(path):
            return

        # the previewer outlives the cell, which may be closed by the time
        # the picture comes
        part = weakref.ref(self)

        def receiver(path, time_ms, image):
            this = part()
            if this is not None:
                this.show(path, image)

        previewer.request(path, time_ms, receiver)

    def _previewer(self):
        """The player's previewer, None while the setting is off or where
        the player has none."""

        if not Settings().get("player/seek_preview"):
            return None

        return getattr(self._block._ctx, "seek_preview", None)

    def show(self, path, image):
        block = self._block

        if sip.isdeleted(block) or block.video_params is None:
            return

        # of the file the cell played when it was asked, not the one it plays
        if block.video_params.uri != path:
            return

        block.overlay.set_preview(image)
