from gridplayer.player.managers.base import ManagerBase
from gridplayer.utils.seek_preview import SeekPreviewer


class SeekPreviewManager(ManagerBase):
    """The one seek previewer of the player, which the videos ask for the
    picture at the time under the mouse on their seek bars: one bar is under
    the mouse at a time, and one process reads for all of them."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self._previewer = SeekPreviewer(parent=self)

    def init(self):
        self._ctx.seek_preview = self._previewer

    def cleanup(self):
        self._previewer.close()
