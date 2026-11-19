"""Favourites opened from Manage Favourites start paused, where they were
kept at, though new videos are set to play as they open; one opened from
the Favourites menu plays, as new videos are set to."""

SETTINGS = {"video_defaults/initial_state": "playing"}


def scenario(d):
    import time

    from gridplayer.models.favourites import FavouriteVideo

    clip = d.media.clips[0]
    kept = FavouriteVideo(name="Kept", path=clip, position=6_000)

    # as Open in Manage Favourites opens it
    manager = next(
        m
        for m in d.player.findChildren(object)
        if type(m).__name__ == "FavouritesManager"
    )
    manager.open_favourites([kept], [], is_paused=True)

    a = d.wait_for_cell("a.mp4")
    d.wait_until(lambda: a.is_playable, "loaded")
    d.wait_until(lambda: abs(a.time - 6_000) < 400, "at where it was kept")

    start = a.time
    time.sleep(1.0)
    d.pump()
    d.check("paused", a.video_params.is_paused, a.video_params.playback_state)
    d.check("not moving", abs(a.time - start) < 200, (start, a.time))

    d.act(a, "Close")
    d.wait_until(lambda: not d.cells, "closed")

    # as the menu opens it
    manager.cmd_open_favourite(kept)
    b = d.wait_for_cell("a.mp4")
    d.wait_until(lambda: b.is_playable, "loaded from the menu")
    d.wait_until(lambda: not b.video_params.is_paused, "plays from the menu")
