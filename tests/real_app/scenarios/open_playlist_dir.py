"""Open Playlist in the folder a playlist was last opened from: a playlist
picked in another folder opens, and that folder is kept for the next time,
in the player's settings."""


def scenario(d):
    from pathlib import Path

    from PyQt5.QtWidgets import QLineEdit

    from gridplayer.models.playlist import Playlist
    from gridplayer.models.video import Video
    from gridplayer.settings import Settings

    clip = d.media.clips[0]
    lists = d.out / "lists"
    lists.mkdir()
    playlist = lists / "mix.gpls"
    playlist.write_text(Playlist(videos=[Video(uri=clip)]).dumps(), encoding="utf-8")

    # last opened from the one above, the playlist picked in the one below it
    Settings().set("player/last_playlist_dir", str(d.out))

    def pick(window):
        d.check(
            "the dialog in the folder last opened from",
            Path(window.directory().absolutePath()) == d.out,
            window.directory().absolutePath(),
        )
        # its name typed in, as a person would: offscreen, its list of the
        # folder is not filled in to pick from
        window.findChild(QLineEdit, "fileNameEdit").setText("lists/mix.gpls")
        window.accept()

    d.through_modal(lambda: d.act(None, "Open Playlist"), "open playlist", pick)

    a = d.wait_for_cell(clip.name)
    d.wait_until(lambda: a.is_playable, "the playlist's video plays")
    d.check(
        "its folder kept, for the next time",
        Settings().sync_get("player/last_playlist_dir") == str(lists),
        Settings().sync_get("player/last_playlist_dir"),
    )
