"""How a player starts another of itself, a new window to move cells into
(see player.managers.new_window): the same program, the same way it was
started itself, told where the cells are.

Read when the command line is, before the settings: nothing here may reach
for them.
"""

import os
import sys

from gridplayer.params import env

# the command line's option for the file the cells are handed over in
MOVED_CELLS_ARG = "--moved-cells"


def new_window_command(moved_cells_file) -> tuple[str, list[str]]:
    """The program to start and its arguments, for a new window to take the
    cells in the file."""

    if env.IS_APPIMAGE:
        # what it runs from is gone once the AppImage it was mounted for
        # closes: the AppImage itself, which mounts its own
        program, args = os.environ["APPIMAGE"], []
    elif env.IS_PYINSTALLER:
        program, args = sys.executable, []
    else:
        program, args = sys.executable, ["-m", "gridplayer"]

    # on the display server this one runs on, picked as it was
    if env.IS_LINUX and env.QT_PLATFORM in ("xcb", "wayland"):
        args += ["--platform", env.QT_PLATFORM]

    return program, [*args, MOVED_CELLS_ARG, str(moved_cells_file)]
