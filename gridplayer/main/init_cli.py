import argparse
import os
import sys
from pathlib import Path

from gridplayer.params import env
from gridplayer.utils.app_dir import ENV_USER_DATA_DIR
from gridplayer.utils.new_window import MOVED_CELLS_ARG
from gridplayer.version import __app_name__, __version__

QT_PLATFORMS = ("auto", "xcb", "wayland")


def init_cli_args(argv=None):
    if argv is None:
        argv = sys.argv[1:]

    parser = argparse.ArgumentParser(
        prog=__app_name__,
        description="Play videos side-by-side",
        epilog="FILE and URL arguments open media files, folders, .gpls"
        " playlists, media lists (.m3u, .m3u8, .pls, .xspf), or streaming URLs"
        " on startup. A folder or a media list plays in one cell, one file"
        " after another.",
    )
    parser.add_argument(
        "files",
        nargs="*",
        metavar="FILE|URL",
        help="media files, folders, .gpls playlists, media lists, or streaming"
        " URLs to open on startup",
    )
    parser.add_argument(
        "--user-data-dir",
        metavar="PATH",
        default="",
        help="store settings and log files in PATH instead of the default"
        f" location (also settable via {ENV_USER_DATA_DIR} environment variable)",
    )
    if env.IS_LINUX:
        parser.add_argument(
            "--platform",
            choices=QT_PLATFORMS,
            default="auto",
            help="display server to run on: auto picks xcb (X11 or Xwayland)"
            " when there is one, wayland otherwise; hardware video needs xcb",
        )
    # not for people: how a player hands cells to the new window it opens
    parser.add_argument(MOVED_CELLS_ARG, metavar="PATH", help=argparse.SUPPRESS)
    parser.add_argument(
        "--version",
        action="version",
        version=f"{__app_name__} {__version__}",
    )

    # Everything after -- is a file however it looks. Split off here
    # because parse_intermixed_args before Python 3.12 rejects -- with
    # nothing but dash prefixed names after it and no file before it
    if "--" in argv:
        dashdash_at = argv.index("--")
        argv, files_after_dashdash = argv[:dashdash_at], argv[dashdash_at + 1 :]
    else:
        files_after_dashdash = []

    args = parser.parse_intermixed_args(argv)

    sys.argv[:] = [sys.argv[0], *args.files, *files_after_dashdash]

    if args.user_data_dir.strip():
        os.environ[ENV_USER_DATA_DIR] = args.user_data_dir.strip()

    if args.moved_cells:
        env.MOVED_CELLS_FILE = Path(args.moved_cells)

    if getattr(args, "platform", "auto") != "auto":
        env.QT_PLATFORM = args.platform
