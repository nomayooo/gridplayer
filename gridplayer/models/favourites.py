"""The viewer's favourite videos, in folders of their own making, as a web
browser keeps its favourites: kept with the player's settings, not with a
playlist, and each opened into the grid as a video of its own.

A favourite is a file on disk, with a name of the viewer's, the A-B loops it
had when it was made a favourite, a loop begun and not finished among them,
and where in it it was, which it is opened with and at again.
"""

from pathlib import Path
from typing import Annotated, Literal

from pydantic import BaseModel, Field, RootModel

# an A-B loop as a video keeps it (models.video.LoopSpan, not imported: the
# settings are made of these, and the video model is made of the settings)
LoopSpan = tuple[int, int | None]

# where a folder is: the index of each folder down to it, () for the top
FolderPath = tuple[int, ...]


class FavouriteVideo(BaseModel):
    kind: Literal["video"] = "video"
    name: str
    path: Path
    loops: list[LoopSpan] = Field(default_factory=list)
    # where a loop begun and not yet finished starts (models.video's
    # loop_start), None for none
    loop_start: int | None = None
    # where in it it was when made a favourite, opened there again: in ms,
    # None for one made before favourites kept it, opened as it opens
    position: int | None = None
    # which loop played, and whether it played outside them, from a seek
    # there (models.video's own)
    loop_index: int = 0
    is_outside_loops: bool = False


class FavouriteFolder(BaseModel):
    kind: Literal["folder"] = "folder"
    name: str
    items: list["FavouriteItem"] = Field(default_factory=list)


FavouriteItem = Annotated[FavouriteVideo | FavouriteFolder, Field(discriminator="kind")]

FavouriteFolder.model_rebuild()


class Favourites(RootModel[list[FavouriteItem]]):
    """The favourites at the top, folders and videos, each folder holding
    more of either."""

    root: list[FavouriteItem] = Field(default_factory=list)

    def __bool__(self) -> bool:
        return bool(self.root)

    def items_at(self, folder: FolderPath) -> list[FavouriteItem]:
        """What a folder holds, the top for (); KeyError for no folder
        there."""

        items = self.root

        for index in folder:
            try:
                item = items[index]
            except IndexError:
                raise KeyError(folder) from None

            if not isinstance(item, FavouriteFolder):
                raise KeyError(folder)

            items = item.items

        return items

    def add(self, folder: FolderPath, item: FavouriteItem) -> None:
        """At the end of a folder, as a browser adds a favourite."""

        self.items_at(folder).append(item)

    def find_video(self, path: Path) -> tuple[FolderPath, FavouriteVideo] | None:
        """The favourite of a file and the folder it is in, None for none."""

        for folder, _ in self.folders():
            for item in self.items_at(folder):
                if isinstance(item, FavouriteVideo) and item.path == path:
                    return folder, item

        return None

    def names_of(self, path: Path) -> set[str]:
        """The names a file is a favourite under, in any folder."""

        return {
            item.name
            for folder, _ in self.folders()
            for item in self.items_at(folder)
            if isinstance(item, FavouriteVideo) and item.path == path
        }

    def put_video(self, folder: FolderPath, video: FavouriteVideo) -> None:
        """A favourite of a file put in a folder, in place of the one of the
        file under the same name: where that one was when it was in the
        folder, else at the end of it, the old one gone. A file is a
        favourite once under each name, so that copies of it, at different
        places in it, are kept apart by theirs."""

        self.put_videos(folder, [video])

    def put_videos(
        self,
        folder: FolderPath,
        videos: list[FavouriteVideo],
        is_folder_only: bool = False,
    ) -> None:
        """Several put in a folder, one after another, as put_video puts one;
        or, folder only, each in place of one of the same name in that
        folder alone, the others elsewhere left, as a playlist imported has
        its videos all in its folder, whichever others have them too.

        The folder's own list is taken once, before any is taken out of it
        or before it: a folder is known by where it is, which that changes,
        so that one taken out above it would leave the next looking for it
        in the wrong place."""

        target = self.items_at(folder)

        for video in videos:
            self._put_into(target, video, is_folder_only)

    def _put_into(
        self, target: list, video: FavouriteVideo, is_folder_only: bool = False
    ) -> None:
        lists = (
            [target]
            if is_folder_only
            else [self.items_at(path) for path, _ in self.folders()]
        )

        is_replaced = False

        for items in lists:
            for index in reversed(range(len(items))):
                item = items[index]

                if not isinstance(item, FavouriteVideo) or (item.path, item.name) != (
                    video.path,
                    video.name,
                ):
                    continue

                if items is target and not is_replaced:
                    items[index] = video
                    is_replaced = True
                else:
                    del items[index]

        if not is_replaced:
            target.append(video)

    def folders(self) -> list[tuple[FolderPath, list[str]]]:
        """Every folder, the top first, each by where it is and the names
        down to it, in the order they are shown."""

        found = [((), [])]

        def walk(items, path, names):
            for index, item in enumerate(items):
                if isinstance(item, FavouriteFolder):
                    folder_path = (*path, index)
                    folder_names = [*names, item.name]
                    found.append((folder_path, folder_names))
                    walk(item.items, folder_path, folder_names)

        walk(self.root, (), [])

        return found


def videos_in(items: list[FavouriteItem]) -> list[FavouriteVideo]:
    """The videos a folder holds itself, not those of its folders."""

    return [item for item in items if isinstance(item, FavouriteVideo)]
