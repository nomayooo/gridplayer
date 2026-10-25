"""The session saved to favourites: the videos of every GridPlayer window
open, each as it is now, in a folder named by the date and time, each
window's in a folder of its own inside it, numbered from 1, this one first,
then the others in the order they were opened. Opened again, as any folder
of folders opens, each window's comes back in a window of its own.

The other windows are asked for theirs (see gridplayer.utils.session_windows),
each serving its own while it is open.
"""

from datetime import datetime

from PyQt5.QtWidgets import QMessageBox

from gridplayer.dialogs.messagebox import QCustomMessageBox
from gridplayer.models.favourites import FavouriteVideo
from gridplayer.player.managers.base import ManagerBase
from gridplayer.utils.app_dir import get_app_data_dir
from gridplayer.utils.qt import count_txt, translate
from gridplayer.utils.session_windows import SessionServer, ask_other_windows

# the name of the folder a session is saved in, when it was saved
SESSION_NAME_FORMAT = "%Y-%m-%d %H:%M:%S"


class SessionManager(ManagerBase):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self._server = None

    @property
    def commands(self):
        return {"save_session": self.cmd_save_session}

    @property
    def _registry_dir(self):
        return get_app_data_dir() / "windows"

    def init(self):
        self._server = SessionServer(
            provider=self._own_videos_data, registry_dir=self._registry_dir, parent=self
        )

        if not self._server.start():
            self._server = None

    def cleanup(self):
        if self._server is not None:
            self._server.stop()
            self._server = None

    def _own_videos_data(self) -> list:
        return [
            video.model_dump(mode="json")
            for video in self._ctx.commands.session_favourites()
        ]

    def _read_window(self, answer) -> list[FavouriteVideo]:
        try:
            return [FavouriteVideo.model_validate(video) for video in answer]
        except (ValueError, TypeError) as e:
            self._log.warning(f"A window's session not read: {e}")
            return []

    def cmd_save_session(self):
        windows = [self._ctx.commands.session_favourites()]

        if self._server is not None:
            answers = ask_other_windows(self._registry_dir, self._server.id)
            windows.extend(self._read_window(answer) for answer in answers)

        windows = [videos for videos in windows if videos]

        if not windows:
            QCustomMessageBox.information(
                self.parent(),
                translate("Favourites", "Save Session"),
                translate("Favourites", "No video files are open to save."),
            )
            return

        # the time here, as the viewer's clock says it
        name = datetime.now().astimezone().strftime(SESSION_NAME_FORMAT)

        self._ctx.commands.save_session_favourites(name, windows)

        QCustomMessageBox.information(
            self.parent(),
            translate("Favourites", "Save Session"),
            translate("Favourites", 'Saved to your favourites as "{NAME}".').format(
                NAME=name
            ),
            buttons=QMessageBox.Ok,
            info=translate("Favourites", "Windows: {WINDOWS}, videos: {VIDEOS}").format(
                WINDOWS=count_txt(len(windows)),
                VIDEOS=count_txt(sum(len(videos) for videos in windows)),
            ),
        )
