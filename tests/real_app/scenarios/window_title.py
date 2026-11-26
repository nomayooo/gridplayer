"""The window's title: a favourites folder opened into an empty window
names it; a window opened from one takes the folder's name; a playlist,
once saved, names it by its file's name, without its extension; its
videos all saved into a folder name it after the folder."""


def _title(d):
    d.pump()
    return d.player.windowHandle().title()


def scenario(d):
    import os
    from pathlib import Path

    from gridplayer.models.favourites import (
        FavouriteFolder,
        Favourites,
        FavouriteVideo,
    )
    from gridplayer.models.moved_cells import MovedCell, MovedCells
    from gridplayer.models.video import Video, VideoBlockMime

    def manager(name):
        return next(
            m for m in d.player.findChildren(object) if type(m).__name__ == name
        )

    favourites = manager("FavouritesManager")
    d.check("nothing open, no name of its own", "Music" not in _title(d), _title(d))

    a_clip, b_clip = d.media.clips[0], d.media.clips[1]
    favourites._save(
        Favourites(
            [
                FavouriteFolder(
                    name="Music", items=[FavouriteVideo(name="A", path=a_clip)]
                )
            ]
        )
    )

    # Favourites > Music > Open All, into this empty window
    favourites.cmd_open_favourites_folder((0,))
    d.wait_for_cell("a.mp4")
    d.check("named after the folder", _title(d).startswith("Music"), _title(d))

    # a playlist saved takes its place
    playlists = manager("PlaylistManager")
    path = Path(os.environ["GP_USER_DATA_DIR"]).parent / "My list.gpl"
    playlists._write_playlist(playlists._make_playlist(), path)
    d.check("the playlist's name", _title(d).startswith("My list"), _title(d))
    d.check("its extension left out", ".gpl" not in _title(d), _title(d))

    d.ctx.commands.force_close_playlist()
    d.wait_until(lambda: not d.cells, "closed")
    d.check("none once closed", not _title(d).startswith("My list"), _title(d))

    # as a new window takes in the videos of a folder opened apart
    moved = Path(os.environ["GP_USER_DATA_DIR"]).parent / "moved.json"
    moved.write_text(
        MovedCells(
            cells=[MovedCell(cell=VideoBlockMime(id="x", video=Video(uri=b_clip)))],
            title="Live",
        ).model_dump_json()
    )
    manager("NewWindowManager").open_moved_cells(moved)
    d.wait_for_cell("b.mp4")
    d.check(
        "a new window named after its folder", _title(d).startswith("Live"), _title(d)
    )

    # all of them saved into a folder: named after it
    from unittest.mock import Mock

    from gridplayer.player.managers import favourites as favourites_module

    favourites_module.AddAllFavouritesDialog.ask = Mock(
        return_value=(favourites.favourites, (0,))
    )
    favourites.cmd_add_all_to_favourites()
    d.check(
        "saved into a folder, named after it", _title(d).startswith("Music"), _title(d)
    )
