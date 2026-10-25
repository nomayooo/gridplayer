"""Playlists imported as favourites: one into a folder of its name, renamed
when asked; two at once into folders of their own names, unasked; a folder
of them opened into the grid, each where its playlist had it, a video in
two of them in both.

The file picker cannot be answered here; what it gives back is set.
"""


def scenario(d):
    from gridplayer.models.favourites import Favourites
    from gridplayer.models.playlist import Playlist
    from gridplayer.models.video import Video
    from gridplayer.player.managers import favourites as manager_module
    from gridplayer.settings import Settings

    Settings().set("favourites", Favourites())

    a_clip, b_clip, c_clip = d.media.clips[:3]
    folder = d.out / "playlists"
    folder.mkdir(exist_ok=True)

    evening = folder / "Evening.gpls"
    Playlist(
        videos=[
            Video(uri=a_clip, current_position=5_000),
            Video(uri=b_clip),
            Video(uri=a_clip, current_position=9_000),
        ],
        save_position=True,
    ).save(evening)
    one = folder / "One.gpls"
    Playlist(videos=[Video(uri=b_clip)]).save(one)
    two = folder / "Two.gpls"
    Playlist(videos=[Video(uri=c_clip)]).save(two)

    picked = []
    manager_module.QFileDialog.getOpenFileNames = lambda *_a, **_k: (
        [str(p) for p in picked],
        "",
    )

    d.open(c_clip)
    c = d.wait_for_cell("c.mp4")
    d.wait_until(lambda: c.is_playable, "c plays")

    # one: its name offered, changed
    picked[:] = [evening]

    def rename(window):
        d.check(
            "its name offered",
            window.line_edit.text() == "Evening",
            window.line_edit.text(),
        )
        window.line_edit.setText("Night")
        window.accept()

    d.through_modal(
        lambda: d.act(c, "Import Playlists to Favourites"), "name it", rename
    )

    root = Settings().get("favourites").root
    d.check("a folder of the name given", [f.name for f in root] == ["Night"], root)
    videos = root[0].items
    d.check(
        "its videos, copies numbered",
        [v.name for v in videos] == ["a.mp4", "b.mp4", "a.mp4 (2)"],
        [v.name for v in videos],
    )

    # two: unasked, each under its own name
    picked[:] = [one, two]
    d.act(c, "Import Playlists to Favourites")
    d.pump()
    names = [f.name for f in Settings().get("favourites").root]
    d.check("two more, named after them", names == ["Night", "One", "Two"], names)

    # the folder opened into the grid, each where the playlist had it
    d.run(c, "open_favourites_folder", (0,))
    d.wait_until(lambda: len(d.cells) == 4, "the folder's three opened")
    first, _, third = d.cells[1:]
    d.wait_until(lambda: first.is_playable and third.is_playable, "they play")
    d.wait_until(lambda: first.time > 4_500, "the first from 5s", timeout=10)
    d.wait_until(lambda: third.time > 8_500, "the third from 9s", timeout=10)
    d.shot("imported and opened")
