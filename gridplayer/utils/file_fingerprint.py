"""What tells a file from another by what is in it, wherever it is: for its
bookmarks to follow it when it is moved or renamed.

Its size, and a hash of its first and last pieces, not of all of it: as
quick for a file of gigabytes as for a small one, a read of a few kilobytes,
once a file, kept for as long as the file is as it was."""

import hashlib
import logging
import os
from pathlib import Path

# how much of its start and of its end is read
PIECE_SIZE = 64 * 1024

# each file's, by where it is and as it was when read: read again only once
# it has changed
_known: dict[tuple[str, int, int], str] = {}


def file_fingerprint(path: Path | str) -> str | None:
    """None for a file that is not there or cannot be read, and for a link,
    which has no file to read."""

    if not isinstance(path, Path):
        return None

    try:
        stat = path.stat()
    except OSError:
        return None

    if not path.is_file():
        return None

    known = (os.path.normcase(os.path.normpath(path)), stat.st_size, stat.st_mtime_ns)

    if known in _known:
        return _known[known]

    try:
        fingerprint = _read(path, stat.st_size)
    except OSError as e:
        logging.getLogger("file_fingerprint").debug(f"Not read: {path}: {e}")
        return None

    _known[known] = fingerprint

    return fingerprint


def _read(path: Path, size: int) -> str:
    digest = hashlib.sha1(usedforsecurity=False)

    with path.open("rb") as file:
        digest.update(file.read(PIECE_SIZE))

        if size > PIECE_SIZE:
            file.seek(max(size - PIECE_SIZE, PIECE_SIZE))
            digest.update(file.read(PIECE_SIZE))

    return f"{size}:{digest.hexdigest()}"
