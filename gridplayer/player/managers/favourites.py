"""Favourite videos, in folders, as a web browser keeps its favourites (see
gridplayer.models.favourites): made from the active video, kept with the
settings, and opened from the Favourites menu into the grid, a video at a
time or a folder's at once; and playlists imported, each as a folder of
its videos."""

from pathlib import Path

from PyQt5.QtCore import pyqtSignal
from PyQt5.QtWidgets import QFileDialog

from gridplayer.dialogs.favourites import (
    AddAllFavouritesDialog,
    AddFavouriteDialog,
    ImportPlaylistsDialog,
    ManageFavouritesDialog,
)
from gridplayer.models.favourites import (
    FavouriteFolder,
    Favourites,
    FavouriteVideo,
    FolderPath,
    folders_within,
    videos_in,
)
from gridplayer.models.playlist import Playlist
from gridplayer.models.video import Video
from gridplayer.player.managers.add_videos import favourite_as_video
from gridplayer.player.managers.base import ManagerBase
from gridplayer.player.managers.recent_list import elide_str
from gridplayer.settings import Settings
from gridplayer.utils.qt import translate

# a name in the menu longer than this is cut short
MENU_NAME_MAX_LENGTH = 60


class FavouritesManager(ManagerBase):
    error = pyqtSignal(str)

    @property
    def commands(self):
        return {
            "add_to_favourites": self.cmd_add_to_favourites,
            "add_all_to_favourites": self.cmd_add_all_to_favourites,
            "import_playlists_to_favourites": self.cmd_import_playlists,
            "manage_favourites": self.cmd_manage_favourites,
            "menu_generator_favourites": self.menu_generator_favourites,
            "menu_generator_favourites_folder": self.menu_generator_favourites_folder,
            "open_favourite": self.cmd_open_favourite,
            "open_favourites_folder": self.cmd_open_favourites_folder,
            "is_favourites_folder_full": self.is_favourites_folder_full,
            "is_any_favourites": self.is_any_favourites,
            "is_any_to_favourite": self.is_any_to_favourite,
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
        items = self._items_at(folder)

        if not videos_in(items) and not folders_within(items):
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
        """A folder's own videos opened here, and those of each folder it
        holds, at any depth, each in a new window of its own."""

        items = self._items_at(folder)

        self.open_favourites(videos_in(items), folders_within(items))

    def open_favourites(self, here: list, apart: list[list]) -> None:
        """Favourites opened, some here, the others each list of them in a
        new window of its own; those whose files are gone said to be."""

        if here:
            self._ctx.commands.add_favourite_videos(here)

        missing = []

        for favourites in apart:
            videos = []

            for favourite in favourites:
                if not favourite.path.is_file():
                    missing.append(str(favourite.path))
                    continue

                video = favourite_as_video(favourite)
                if video is not None:
                    videos.append(video)

            if videos:
                self._ctx.commands.open_in_new_window(videos)

        if missing:
            self.error.emit(
                "{}\n\n{}".format(
                    translate("Error", "File not found!"), "\n".join(missing)
                )
            )

    # making and keeping them

    def is_any_to_favourite(self) -> bool:
        """A file to make a favourite: among the cells picked out, if any
        are, else the active one."""

        selected = self._ctx.commands.selected_cells()

        if selected:
            return any(block.is_local_file for block in selected)

        block = self._ctx.active_block

        return block is not None and block.is_local_file

    def cmd_add_to_favourites(self) -> None:
        """The active video made a favourite; or the cells picked out
        (Ctrl+Click), if any are, all at once into a folder, as Add All."""

        selected = self._ctx.commands.selected_cells()

        if selected:
            self._add_many(selected, is_selected=True)
            return

        block = self._ctx.active_block

        if block is None or not block.is_local_file:
            return

        params = block.video_params
        favourites = self.favourites

        # a favourite already: offered as it is, to be replaced
        kept = favourites.find_video(params.uri)
        folder, name = ((), _name_of(block))
        if kept is not None:
            folder, name = kept[0], kept[1].name

        added = AddFavouriteDialog.ask(
            parent=self.parent(),
            favourites=favourites,
            name=name,
            loops=len(params.loops),
            loop_start=params.loop_start,
            position=params.current_position,
            folder=folder,
            kept_names=frozenset(favourites.names_of(params.uri)),
        )

        if added is None:
            return

        favourites, folder, name = added

        favourites.put_video(folder, _favourite_of(block, name))

        self._save(favourites)

    def cmd_add_all_to_favourites(self) -> None:
        """Every video open that is a file, in the grid's order, made a
        favourite under its own name in the folder picked; one already a
        favourite replaced, as when it is made one on its own."""

        blocks = self._ctx.video_blocks.blocks_for_ids(
            self._ctx.commands.layout_order()
        )

        self._add_many(blocks)

    def _add_many(self, blocks: list, is_selected: bool = False) -> None:
        files = [block for block in blocks if block.is_local_file]

        if not files:
            return

        added = AddAllFavouritesDialog.ask(
            parent=self.parent(),
            favourites=self.favourites,
            count=len(files),
            left_out=len(blocks) - len(files),
            is_selected=is_selected,
        )

        if added is None:
            return

        favourites, folder = added

        favourites.put_videos(
            folder, _numbered([_favourite_of(block) for block in files])
        )

        self._save(favourites)

    def cmd_import_playlists(self) -> None:
        """Playlists made favourites, each a folder of its videos named after
        it, in a folder of the viewer's picking: one alone under a name the
        viewer may change, several under their own. A folder of the name
        already there is filled again, each of its videos replaced as a
        favourite of the same name is."""

        paths = self._ask_playlists()

        if not paths:
            return

        asked = ImportPlaylistsDialog.ask(
            parent=self.parent(),
            favourites=self.favourites,
            names=[path.stem for path in paths],
        )

        if asked is None:
            return

        favourites, into, names = asked
        problems = []

        for path, name in zip(paths, names):
            try:
                playlist = Playlist.read(path)
            except (OSError, ValueError) as e:
                self._log.error(f"Playlist not imported: {path}: {e}")
                problems.append(
                    translate("Favourites", "Couldn't read {NAME}").format(
                        NAME=path.name
                    )
                )
                continue

            # streams and links, which favourites are not made of
            videos = [v for v in playlist.videos or [] if isinstance(v.uri, Path)]

            if not videos:
                problems.append(
                    translate("Favourites", "No video files in {NAME}").format(
                        NAME=path.name
                    )
                )
                continue

            # a playlist saved without where its videos were (the default)
            # says 0 for each: none, for each to open as a new one would
            made = [
                _favourite_of_video(video).model_copy(
                    update={"position": video.current_position or None}
                )
                for video in videos
            ]

            # each playlist's folder with all its videos, those in others too
            favourites.put_videos(
                _sub_folder(favourites, into, name),
                _numbered(made),
                is_folder_only=True,
            )

        self._save(favourites)

        if problems:
            self.error.emit("\n".join(problems))

    def _ask_playlists(self) -> list[Path]:
        files, _ = QFileDialog.getOpenFileNames(
            self.parent(),
            translate("Favourites", "Import Playlists"),
            "",
            "{} (*.gpls)".format(
                translate(
                    "Dialog - Open Playlist", "GridPlayer Playlists", "File format"
                )
            ),
        )

        return [Path(file) for file in files]

    def cmd_manage_favourites(self) -> None:
        edited = ManageFavouritesDialog.edit(
            parent=self.parent(),
            favourites=self.favourites,
            on_open=self.open_favourites,
        )

        if edited is not None:
            self._save(edited)


def _name_of(block) -> str:
    """The name a cell's video is a favourite under, unless given another:
    the one the cell shows, else the file's."""

    return block.title or Path(block.video_params.uri).stem


def _numbered(made: list[FavouriteVideo]) -> list[FavouriteVideo]:
    """Copies of one file, at different places in it, each kept under a name
    of its own: "A", "A (2)", "A (3)", in the order given; the same names
    again the next time, to be replaced as any are."""

    copies: dict = {}
    numbered = []

    for video in made:
        copies[video.path] = copies.get(video.path, 0) + 1
        count = copies[video.path]

        if count > 1:
            video = video.model_copy(update={"name": f"{video.name} ({count})"})

        numbered.append(video)

    return numbered


def _sub_folder(favourites: Favourites, parent: FolderPath, name: str) -> FolderPath:
    """The folder of the name in the one given, made at the end of it if
    there is none."""

    items = favourites.items_at(parent)

    for index, item in enumerate(items):
        if isinstance(item, FavouriteFolder) and item.name == name:
            return (*parent, index)

    items.append(FavouriteFolder(name=name))

    return (*parent, len(items) - 1)


def _favourite_of(block, name: str | None = None) -> FavouriteVideo:
    """The video a cell plays, as a favourite: its file, its loops, where
    it is in it, under the name given, else the one the cell shows, else
    the file's."""

    return _favourite_of_video(block.video_params, name or _name_of(block))


def _favourite_of_video(params: Video, name: str | None = None) -> FavouriteVideo:
    """A video as a playlist keeps it, as a favourite, under the name given,
    else its title, else its file's name."""

    return FavouriteVideo(
        name=name or params.title or Path(params.uri).name,
        path=params.uri,
        loops=list(params.loops),
        loop_start=params.loop_start,
        position=params.current_position,
        loop_index=params.loop_index,
        is_outside_loops=params.is_outside_loops,
    )
