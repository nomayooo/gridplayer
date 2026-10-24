"""Cells picked out (Ctrl+Click, or Select in a cell's menu) and moved to a
new window: another player, started for them, which takes each as it was,
its place in the video, its loops, its bookmarks and its list along, as a
cell dragged to another player comes; and gone from this one.

The new window is a playlist of no file, closed without being asked about,
until it is saved.
"""

import os
import tempfile
from pathlib import Path

from PyQt5.QtCore import QProcess, pyqtSignal

from gridplayer.models.media_list import as_path
from gridplayer.models.moved_cells import MovedCell, MovedCells
from gridplayer.player.managers.base import ManagerBase
from gridplayer.utils.new_window import new_window_command
from gridplayer.utils.qt import translate


class NewWindowManager(ManagerBase):
    # the videos moved into this window, for the grid to lay out
    cells_moved_in = pyqtSignal(list)

    error = pyqtSignal(str)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        # the cells picked out, by id
        self._selected: list[str] = []

    @property
    def commands(self):
        return {
            "toggle_cell_selected": self.cmd_toggle_cell_selected,
            "clear_cell_selection": self.cmd_clear_cell_selection,
            "is_active_cell_selected": self.is_active_cell_selected,
            "is_any_cells_selected": self.is_any_cells_selected,
            "move_to_new_window": self.cmd_move_to_new_window,
            "open_moved_cells": self.open_moved_cells,
        }

    # picking them out

    def cmd_toggle_cell_selected(self):
        block = self._ctx.active_block

        if block is None:
            return

        if block.id in self._selected:
            self._selected.remove(block.id)
            block.is_selected = False
        else:
            self._selected.append(block.id)
            block.is_selected = True

    def cmd_clear_cell_selection(self):
        for block in self._selected_blocks():
            block.is_selected = False

        self._selected = []

    def is_active_cell_selected(self) -> bool:
        block = self._ctx.active_block

        return block is not None and block.id in self._selected

    def is_any_cells_selected(self) -> bool:
        return bool(self._selected_blocks())

    def forget_cells_gone(self):
        """The cells closed meanwhile no longer picked out."""

        self._selected = [
            block_id
            for block_id in self._selected
            if self._ctx.video_blocks.by_id(block_id) is not None
        ]

    def _selected_blocks(self) -> list:
        """The cells picked out, in the order the grid has them."""

        in_grid = self._ctx.video_blocks.blocks_for_ids(
            self._ctx.commands.layout_order()
        )

        return [block for block in in_grid if block.id in self._selected]

    # moving them out

    def cmd_move_to_new_window(self):
        """The cells picked out, or else the active one, into a new window,
        and out of this one."""

        blocks = self._selected_blocks()

        if not blocks and self._ctx.active_block is not None:
            blocks = [self._ctx.active_block]

        blocks = [block for block in blocks if block.video_params is not None]

        if not blocks:
            return

        moved = MovedCells(
            cells=[
                MovedCell(cell=block.drag_data, media_list=block.media_list)
                for block in blocks
            ]
        )

        moved_file = _write_moved_cells(moved)

        program, args = new_window_command(moved_file)

        is_started, _ = QProcess.startDetached(program, args)

        if not is_started:
            self._log.error(f"Couldn't start a new window: {program} {args}")
            moved_file.unlink(missing_ok=True)
            self.error.emit(translate("Error", "Couldn't open a new window!"))
            return

        self.cmd_clear_cell_selection()

        for block in blocks:
            block.close()

    # taking them in

    def open_moved_cells(self, moved_file: Path):
        """The cells another player moved into this new window, each as it
        was there."""

        try:
            moved = MovedCells.model_validate_json(moved_file.read_bytes())
        except (OSError, ValueError) as e:
            self._log.error(f"Moved cells not read: {e}")
            self.error.emit(translate("Error", "Couldn't open the moved videos!"))
            return
        finally:
            moved_file.unlink(missing_ok=True)

        videos = []

        for moved_cell in moved.cells:
            video = moved_cell.cell.video

            # a file comes over as its path in text, as a link would
            video.uri = as_path(video.uri)

            # its list there before it is, for it to find as it opens
            if moved_cell.media_list is not None:
                video.list_id = self._ctx.lists.add(moved_cell.media_list).id

            videos.append(video)

        self.cells_moved_in.emit(videos)

        for moved_cell in moved.cells:
            video = moved_cell.cell.video

            if self._ctx.video_blocks.by_video_id(video.id) is not None:
                self._ctx.bookmarks.add(video.uri, video.id, moved_cell.cell.bookmarks)
            elif moved_cell.media_list is not None:
                # a full grid turned it away, and its list with it
                self._ctx.lists.drop_if_untaken(video.list_id)

        # nothing to be asked about on closing it, until it is saved
        self._ctx.commands.set_playlist_scratch()


def _write_moved_cells(moved: MovedCells) -> Path:
    """The file they are handed over in, which the new window removes once
    it has read it."""

    handle, name = tempfile.mkstemp(prefix="gridplayer-moved-", suffix=".json")

    with os.fdopen(handle, "w", encoding="utf-8") as f:
        f.write(moved.model_dump_json())

    return Path(name)
