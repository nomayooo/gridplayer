from PyQt5.QtCore import QTimer, pyqtSignal

from gridplayer.params import env
from gridplayer.player.managers.base import ManagerBase
from gridplayer.settings import Settings
from gridplayer.utils.qt import qt_connect
from gridplayer.utils.single_instance import Listener


class InstanceListenerManager(ManagerBase):
    files_opened = pyqtSignal(list)
    activate_requested = pyqtSignal()

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self._instance_listener = Listener()

        qt_connect(
            (self._instance_listener.activate, self.activate_requested),
            (self._instance_listener.open_files, self.files_opened),
        )

    def init(self):
        if not Settings().get("player/one_instance"):
            return

        # a window cells were moved into: the files sent to the player go to
        # the one it came from, which is listening already
        if env.MOVED_CELLS_FILE is not None:
            return

        QTimer.singleShot(0, self._instance_listener.start)

    def cleanup(self):
        self._instance_listener.cleanup()
