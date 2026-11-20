"""ffmpeg, for exporting loops (see utils.loop_export): one fetched for the
player before, in its data folder, else one the system has. On Windows,
where few have it, fetched on first use, once asked: a build of it from
where Windows builds of ffmpeg are usually had, checked against the
checksum published with it before it is kept.

The fetching is plain: no Qt here, for it to run in a thread of its own and
be tested without the player.
"""

import hashlib
import logging
import shutil
import zipfile
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from gridplayer.params import env

_log = logging.getLogger(__name__)

FOLDER_NAME = "ffmpeg"

CHUNK_SIZE = 256 * 1024


@dataclass(frozen=True)
class Source:
    """Where a Windows build of ffmpeg is fetched from: the zip, and the
    checksum of it, published beside it."""

    zip_url: str
    sha256_url: str


# tried in turn, the next where one cannot be had
WINDOWS_SOURCES = (
    Source(
        "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip",
        "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip.sha256",
    ),
    Source(
        "https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/"
        "ffmpeg-master-latest-win64-gpl.zip",
        "https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/"
        "checksums.sha256",
    ),
)


def _exe_name() -> str:
    return "ffmpeg.exe" if env.IS_WINDOWS else "ffmpeg"


def fetched_path(data_dir: Path) -> Path:
    """Where one fetched for the player is kept."""

    return data_dir / FOLDER_NAME / _exe_name()


def find_ffmpeg(data_dir: Path) -> Path | None:
    """One fetched for the player before, else the system's; None for
    none."""

    fetched = fetched_path(data_dir)
    if fetched.is_file():
        return fetched

    found = shutil.which("ffmpeg")

    return None if found is None else Path(found)


def can_fetch() -> bool:
    """Fetched for the player only on Windows: elsewhere it is the
    system's to have, from its packages."""

    return env.IS_WINDOWS


class FetchCancelled(Exception):
    pass


class FetchFailed(Exception):
    pass


def fetch_ffmpeg(
    data_dir: Path,
    session,
    on_progress: Callable[[int, int | None], None] = lambda _done, _total: None,
    is_cancelled: Callable[[], bool] = lambda: False,
    sources=WINDOWS_SOURCES,
) -> Path:
    """ffmpeg fetched into the data folder, from the first of the sources
    that can be had, its zip checked against its checksum; where it is
    then. A requests session does the fetching. Nothing is kept of one
    cancelled or failed."""

    errors = []

    for source in sources:
        if is_cancelled():
            raise FetchCancelled

        try:
            return _fetch_from(source, data_dir, session, on_progress, is_cancelled)
        except FetchCancelled:
            raise
        except (OSError, ValueError, zipfile.BadZipFile, FetchFailed) as e:
            _log.warning(f"ffmpeg not fetched from {source.zip_url}: {e}")
            errors.append(f"{source.zip_url}: {e}")

    raise FetchFailed("\n".join(errors) or "no source")


def _fetch_from(source, data_dir, session, on_progress, is_cancelled) -> Path:
    folder = data_dir / FOLDER_NAME
    folder.mkdir(parents=True, exist_ok=True)

    expected = _published_sha256(session, source)

    part = folder / "download.part"

    try:
        digest = _download(session, source.zip_url, part, on_progress, is_cancelled)

        if digest != expected:
            raise FetchFailed(f"checksum {digest} is not the one published")

        target = fetched_path(data_dir)
        _unpack_exe(part, target)
    finally:
        part.unlink(missing_ok=True)

    return target


def _published_sha256(session, source: Source) -> str:
    """The zip's checksum as published: a file of the one checksum, or of
    one per file, the zip's by its name."""

    response = session.get(source.sha256_url, timeout=30)
    response.raise_for_status()

    zip_name = source.zip_url.rsplit("/", 1)[-1]

    for line in response.text.splitlines():
        fields = line.split()

        if not fields:
            continue

        if len(fields) == 1 or fields[-1].lstrip("*") == zip_name:
            checksum = fields[0].lower()
            if len(checksum) == 64 and all(c in "0123456789abcdef" for c in checksum):
                return checksum

    raise FetchFailed("no checksum published for it")


def _download(session, url, path: Path, on_progress, is_cancelled) -> str:
    digest = hashlib.sha256()

    with session.get(url, stream=True, timeout=30) as response:
        response.raise_for_status()

        total = response.headers.get("Content-Length")
        total = int(total) if total and total.isdigit() else None
        done = 0

        with path.open("wb") as file:
            for chunk in response.iter_content(CHUNK_SIZE):
                if is_cancelled():
                    raise FetchCancelled

                file.write(chunk)
                digest.update(chunk)
                done += len(chunk)
                on_progress(done, total)

    return digest.hexdigest()


def _unpack_exe(zip_path: Path, target: Path) -> None:
    """The ffmpeg program alone taken out of the zip, wherever it is in
    it (bin/ffmpeg.exe, under a folder named for the build)."""

    with zipfile.ZipFile(zip_path) as archive:
        names = [
            name
            for name in archive.namelist()
            if name.replace("\\", "/").rsplit("/", 1)[-1].lower() == _exe_name()
        ]

        if not names:
            raise FetchFailed("no ffmpeg in it")

        # the one in bin/, where there are more
        name = next((n for n in names if "/bin/" in n.replace("\\", "/")), names[0])

        part = target.with_suffix(target.suffix + ".part")

        with archive.open(name) as src, part.open("wb") as dst:
            shutil.copyfileobj(src, dst)

    if not env.IS_WINDOWS:
        part.chmod(0o755)

    part.replace(target)
