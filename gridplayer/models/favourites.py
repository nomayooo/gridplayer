"""The viewer's favourite videos, in folders of their own making, as a web
browser keeps its favourites: kept with the player's settings, not with a
playlist, and each opened into the grid as a video of its own.

A favourite is a file on disk, with a name of the viewer's and the A-B loops
it had when it was made a favourite, which it is opened with again.
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
