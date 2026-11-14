"""The A-B loops last left on each file, kept with the player's settings, so
that a file opened again, in whatever playlist or cell, from a favourite or
not, has them there again.

A file is known by utils.bookmarks.file_key, as its bookmarks are: a path
whatever the case of its letters on Windows, a YouTube video by its id.
Only the files most recently looped are kept, the oldest let go first.
"""

from pydantic import BaseModel, Field

# an A-B loop as a video keeps it (models.video.LoopSpan, not imported: the
# settings are made of these, and the video model is made of the settings)
LoopSpan = tuple[int, int | None]

# how many files' loops are kept, the ones looped longest ago let go
MAX_FILES = 2000


class FileLoops(BaseModel):
    loops: list[LoopSpan] = Field(default_factory=list)
    # where a loop begun and not yet finished starts, None for none
    loop_start: int | None = None

    def __bool__(self) -> bool:
        return bool(self.loops) or self.loop_start is not None


class RememberedLoops(BaseModel):
    # by file key, the one looped last at the end
    files: dict[str, FileLoops] = Field(default_factory=dict)

    def __bool__(self) -> bool:
        return bool(self.files)

    def get(self, key: str) -> FileLoops | None:
        return self.files.get(key)

    def put(self, key: str, entry: FileLoops) -> None:
        """A file's loops as they are now; none at all forgets the file."""

        self.files.pop(key, None)

        if not entry:
            return

        self.files[key] = entry

        while len(self.files) > MAX_FILES:
            del self.files[next(iter(self.files))]
