"""Favourite videos, in folders, as a web browser keeps its favourites (see
gridplayer.models.favourites): made from the active video, kept with the
settings, and opened from the Favourites menu into the grid, a video at a
time or a folder's at once."""

from pathlib import Path

from gridplayer.dialogs.favourites import AddFavouriteDialog, ManageFavouritesDialog
from gridplayer.models.favourites import (
    FavouriteFolder,
    Favourites,
    FavouriteVideo,
    FolderPath,
    videos_in,
)
from gridplayer.player.managers.base import ManagerBase
from gridplayer.player.managers.recent_list import elide_str
from gridplayer.settings import Settings
from gridplayer.utils.qt import translate

# a name in the menu longer than this is cut short
MENU_NAME_MAX_LENGTH = 60


class FavouritesManager(ManagerBase):
    @property
    def commands(self):
        return {
            "add_to_favourites": self.cmd_add_to_favourites,
            "manage_favourites": self.cmd_manage_favourites,
            "menu_generator_favourites": self.menu_generator_favourites,
            "menu_generator_favourites_folder": self.menu_generator_favourites_folder,
            "open_favourite": self.cmd_open_favourite,
            "open_favourites_folder": self.cmd_open_favourites_folder,
            "is_favourites_folder_full": self.is_favourites_folder_full,
            "is_any_favourites": self.is_any_favourites,
        }

    @property
    def favourites(self) -> Favourites:
        return Settings().get("favourites")

    def _save(self, favourites: Favourites) -> None:
        Settings().set("favourites", favourites)

    def is_any_favourites(self) -> bool:
        return bool(self.favourites)

    # menus

    def menu_generator_favourites(self):
        return self._menu_of(())

    def menu_generator_favourites_folder(self, folder: FolderPath):
        menu = self._menu_of(folder)

        if not videos_in(self._items_at(folder)):
            return menu

        return [
            *menu,
            "---",
            {
                "title": translate("Favourites", "Open All"),
                "icon": "add-files",
                "func": ("open_favourites_folder", folder),
            },
        ]

    def is_favourites_folder_full(self, folder: FolderPath) -> bool:
        return bool(self._items_at(folder))

    def _menu_of(self, folder: FolderPath):
        menu = []

        for index, item in enumerate(self._items_at(folder)):
            title = elide_str(item.name, MENU_NAME_MAX_LENGTH)

            if isinstance(item, FavouriteFolder):
                path = (*folder, index)
                menu.append(
                    {
                        "title": title,
                        "icon": "favourites-folder",
                        "menu_generator": ("menu_generator_favourites_folder", path),
                        # an empty one is shown, greyed out, rather than left out
                        "enable_if": ("is_favourites_folder_full", path),
                    }
                )
            else:
                menu.append(
                    {
                        "title": title,
                        "icon": "add-files",
                        "func": ("open_favourite", item),
                    }
                )

        return menu

    def _items_at(self, folder: FolderPath):
        try:
            return self.favourites.items_at(folder)
        except KeyError:
            return []

    # opening

    def cmd_open_favourite(self, favourite: FavouriteVideo) -> None:
        self._ctx.commands.add_favourite_videos([favourite])

    def cmd_open_favourites_folder(self, folder: FolderPath) -> None:
        videos = videos_in(self._items_at(folder))

        if videos:
            self._ctx.commands.add_favourite_videos(videos)

    # making and keeping them

    def cmd_add_to_favourites(self) -> None:
        block = self._ctx.active_block

        if block is None or not block.is_local_file:
            return

        params = block.video_params
        favourites = self.favourites

        # a favourite already: offered as it is, to be replaced
        kept = favourites.find_video(params.uri)
        folder, name = ((), block.title or Path(params.uri).stem)
        if kept is not None:
            folder, name = kept[0], kept[1].name

        added = AddFavouriteDialog.ask(
            parent=self.parent(),
            favourites=favourites,
            name=name,
            loops=len(params.loops),
            loop_start=params.loop_start,
            folder=folder,
            is_kept=kept is not None,
        )

        if added is None:
            return

        favourites, folder, name = added

        favourites.put_video(
            folder,
            FavouriteVideo(
                name=name,
                path=params.uri,
                loops=list(params.loops),
                loop_start=params.loop_start,
            ),
        )

        self._save(favourites)

    def cmd_manage_favourites(self) -> None:
        edited = ManageFavouritesDialog.edit(
            parent=self.parent(), favourites=self.favourites
        )

        if edited is not None:
            self._save(edited)
