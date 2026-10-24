"""Files deleted for good, as Shift+Delete deletes them in a file manager: the
picked cells' (Ctrl+Click), or else the active one's, once asked, and not
moved to the trash.

Each cell showing one is closed first, for its player to let go of it: a
file a player has open cannot be deleted on Windows. Its player may take a
moment to, so a file still held is tried again for a while before giving
up on it.
"""

from pathlib import Path

from PyQt5.QtCore import QTimer, pyqtSignal
from PyQt5.QtWidgets import QMessageBox

from gridplayer.dialogs.messagebox import QCustomMessageBox
from gridplayer.player.managers.base import ManagerBase
from gridplayer.utils.qt import count_txt, translate

RETRY_INTERVAL_MS = 250
RETRY_TIMES = 20


class DeleteFilesManager(ManagerBase):
    error = pyqtSignal(str)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        # the files still to be deleted, with the tries left for each
        self._pending: dict[Path, int] = {}

        self._retry_timer = QTimer(self)
        self._retry_timer.setInterval(RETRY_INTERVAL_MS)
        self._retry_timer.timeout.connect(self._delete_pending)

    @property
    def commands(self):
        return {
            "is_any_to_delete": self.is_any_to_delete,
            "delete_files": self.cmd_delete_files,
        }

    def is_any_to_delete(self) -> bool:
        return bool(self._files())

    def _files(self) -> list[Path]:
        """The files of the cells picked out, or else of the active one, each
        once, in the grid's order."""

        blocks = self._ctx.commands.selected_cells()

        if not blocks and self._ctx.active_block is not None:
            blocks = [self._ctx.active_block]

        files = []

        for block in blocks:
            params = block.video_params

            if params is None or not isinstance(params.uri, Path):
                continue

            if params.uri not in files:
                files.append(params.uri)

        return files

    def cmd_delete_files(self):
        files = self._files()

        if not files or not self._is_sure(files):
            return

        self._ctx.commands.clear_cell_selection()

        for block in list(self._ctx.video_blocks):
            if block.video_params is not None and block.video_params.uri in files:
                block.close()

        for path in files:
            self._pending[path] = RETRY_TIMES

        self._delete_pending()

    def _is_sure(self, files: list[Path]) -> bool:
        if len(files) == 1:
            question = translate("Actions", 'Permanently delete "{NAME}"?').format(
                NAME=files[0].name
            )
        else:
            question = translate("Actions", "Permanently delete {COUNT} files?").format(
                COUNT=count_txt(len(files))
            )

        answer = QCustomMessageBox.question(
            self.parent(),
            translate("Actions", "Delete File"),
            question,
            info=translate(
                "Actions", "It won't go to the Recycle Bin, and can't be undone."
            ),
        )

        return answer == QMessageBox.Yes

    def _delete_pending(self):
        for path, tries_left in list(self._pending.items()):
            try:
                path.unlink(missing_ok=True)
            except PermissionError as e:
                # still held by the player closing on it, on Windows
                if tries_left > 1:
                    self._pending[path] = tries_left - 1
                    continue

                self._failed(path, e)
            except OSError as e:
                self._failed(path, e)
            else:
                self._log.info(f"Deleted {path}")

            del self._pending[path]

        if self._pending:
            self._retry_timer.start()
        else:
            self._retry_timer.stop()

    def _failed(self, path: Path, e: OSError):
        self._log.error(f"Couldn't delete {path}: {e}")

        message = translate("Error", 'Couldn\'t delete "{NAME}"!').format(
            NAME=path.name
        )

        self.error.emit(f"{message}\n\n{e.strerror or e}")
