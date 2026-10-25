"""A favourites folder opened, from its menu's Open All and from Manage
Favourites: its own videos here, and the videos of each folder it holds, at
any depth, in a new window each, each where it was kept.

A new window is another process, which a scenario cannot drive: its start
is caught here, what it is handed read, and one taken in by this player as
the new one would take it.
"""


def scenario(d):
    from pathlib import Path

    from gridplayer.models.favourites import (
        FavouriteFolder,
        Favourites,
        FavouriteVideo,
    )
    from gridplayer.models.moved_cells import MovedCells
    from gridplayer.player.managers import new_window
    from gridplayer.settings import Settings

    a_clip, b_clip, c_clip = d.media.clips[:3]
    Settings().set(
        "favourites",
        Favourites(
            [
                FavouriteFolder(
                    name="Playlists",
                    items=[
                        FavouriteVideo(name="Own", path=c_clip),
                        FavouriteFolder(
                            name="One",
                            items=[
                                FavouriteVideo(name="A", path=a_clip, position=6_000),
                                FavouriteVideo(name="B", path=b_clip),
                            ],
                        ),
                        FavouriteFolder(
                            name="Two",
                            items=[
                                FavouriteFolder(
                                    name="Deep",
                                    items=[FavouriteVideo(name="C", path=c_clip)],
                                )
                            ],
                        ),
                    ],
                )
            ]
        ),
    )

    started = []

    def start_detached(program, args):
        started.append(Path(args[args.index("--moved-cells") + 1]))
        return True

    new_window.QProcess.startDetached = start_detached

    d.open(a_clip)
    a = d.wait_for_cell("a.mp4")
    d.wait_until(lambda: a.is_playable, "a plays")

    def handed(path):
        moved = MovedCells.model_validate_json(path.read_bytes())
        return [Path(str(m.cell.video.uri)).name for m in moved.cells]

    # from the menu
    menu = d.menu(a, "menu_generator_favourites")
    d.check("the folder listed", menu == ["Playlists"], menu)
    d.run(a, "open_favourites_folder", (0,))
    d.wait_until(lambda: len(d.cells) == 2, "its own opened here")
    d.check("its own here", d.cells[1].video_params.uri == c_clip)
    d.check("two windows started", len(started) == 2, started)
    windows = [handed(p) for p in started]
    d.check(
        "One's in one, Deep's in another",
        windows == [["a.mp4", "b.mp4"], ["c.mp4"]],
        windows,
    )

    # as the new window takes One's in
    d.player.open_moved_cells(started[0])
    d.wait_until(lambda: len(d.cells) == 4, "taken in")
    taken = d.cells[2]
    d.wait_until(lambda: taken.is_playable, "it plays")
    d.wait_until(lambda: taken.time > 5_500, "from where it was kept", timeout=10)
    d.check("from 6s", taken.time > 5_500, taken.time)

    # from the manager; the other window's file let go, none to take it
    for path in started:
        path.unlink(missing_ok=True)
    started.clear()

    def open_folder(window):
        window.tree.topLevelItem(0).setSelected(True)
        window.open_button.click()
        d.wait_until(lambda: len(started) == 2, "two more windows")
        window.reject()

    d.through_modal(lambda: d.act(a, "Manage Favourites"), "manage", open_folder)
    d.check("the same from the manager", [handed(p) for p in started] == windows)
    d.wait_until(lambda: len(d.cells) == 5, "its own opened here again")
    for path in started:
        path.unlink(missing_ok=True)
