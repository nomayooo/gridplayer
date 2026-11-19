"""The moving pictures of ClipPreviewer (see clip_preview), played by VLC in
the process it keeps: no Qt in here, for the process to start as quickly as
it can.

A file is played without sound and scaled down, a few seconds at each of the
places it is asked to show, one after another and round again; its frames
sent as they come, at most so many a second, the last one only where more
came meanwhile.
"""

import ctypes
import threading
import time
from pathlib import Path

from gridplayer.utils.seek_preview_reader import _VideoFormatCb, preview_size

# how big the frames are, at most
CLIP_PREVIEW_PX = 320

# how many frames a second are sent, at most
FRAMES_PER_S = 20

# a file that has shown nothing in this long is given up on
OPEN_TIMEOUT_S = 4.0


def serve(conn):
    """Run in the process ClipPreviewer keeps. Asked:

    ("play", token, path, places, seconds): the file played, `seconds` at
    each of the places (fractions of its length) in turn, round and round;
    ("stop",): stopped; None: the process ends.

    Answers ("frame", token, width, height, frame bytes) as it plays, and
    ("failed", token) for a file that shows nothing.
    """

    from gridplayer.vlc_player.libvlc import vlc

    options = [
        "--intf=dummy",
        "--quiet",
        "--no-audio",
        "--no-spu",
        "--no-osd",
        "--no-lua",
        "--no-interact",
        "--no-sub-autodetect-file",
        "--no-video-title-show",
        # the GPU is for the videos
        "--avcodec-hw=none",
    ]

    if (
        vlc.plugin_path is not None
        and (Path(vlc.plugin_path) / "plugins.dat").is_file()
    ):
        options.append("--no-plugins-scan")

    player = _ClipPlayer(vlc, vlc.Instance(options))

    try:
        _loop(conn, player)
    except (EOFError, OSError):
        pass
    finally:
        player.stop()


def _loop(conn, player):
    playing = None

    while True:
        if conn.poll(1 / FRAMES_PER_S if playing else None):
            asked = conn.recv()

            # only the last one asked by now is done
            while asked is not None and conn.poll():
                asked = conn.recv()

            if asked is None:
                return

            if asked[0] == "stop":
                player.stop()
                playing = None
            else:
                _, token, path, places, seconds = asked
                player.play(path)
                playing = _Playing(token, places, seconds)
            continue

        if playing is None:
            continue

        frame = player.take_frame()

        if frame is not None:
            playing.is_shown = True
            conn.send(("frame", playing.token, *frame))
        elif not playing.is_shown and playing.waited() > OPEN_TIMEOUT_S:
            conn.send(("failed", playing.token))
            player.stop()
            playing = None
            continue

        if playing.is_due():
            player.go_to(playing.next_place())


class _Playing:
    """Where a file being shown is in going round its places."""

    def __init__(self, token, places, seconds):
        self.token = token
        self.places = list(places) or [0.0]
        self.seconds = seconds
        self.is_shown = False

        self._index = -1
        self._started = time.monotonic()
        # the first place gone to as soon as the file shows
        self._switched = None

    def waited(self) -> float:
        return time.monotonic() - self._started

    def is_due(self) -> bool:
        if not self.is_shown:
            return False

        return (
            self._switched is None or time.monotonic() - self._switched >= self.seconds
        )

    def next_place(self) -> float:
        self._index = (self._index + 1) % len(self.places)
        self._switched = time.monotonic()
        return self.places[self._index]


class _ClipPlayer:
    """A VLC player drawing into a buffer of ours, scaled down; the last
    frame drawn kept for the loop to take."""

    def __init__(self, vlc, instance):
        self._vlc = vlc
        self._instance = instance
        self._player = instance.media_player_new()
        self._path = None

        self._lock = threading.Lock()
        self._buffer = None
        self._size = (0, 0)
        self._frame = None

        self._format_cb = self._make_format_cb()
        self._cleanup_cb = vlc.CallbackDecorators.VideoCleanupCb(lambda opaque: None)
        self._lock_cb = vlc.CallbackDecorators.VideoLockCb(self._on_lock)
        self._unlock_cb = vlc.CallbackDecorators.VideoUnlockCb(lambda *_: None)
        self._display_cb = vlc.CallbackDecorators.VideoDisplayCb(self._on_display)

        self._player.video_set_callbacks(
            self._lock_cb, self._unlock_cb, self._display_cb, None
        )
        self._player.video_set_format_callbacks(self._format_cb, self._cleanup_cb)

    def play(self, path: str):
        self.stop()

        media = self._instance.media_new_path(path)
        media.add_option(":no-audio")
        # round again from a place, not stopped at the end
        media.add_option(":input-repeat=65535")
        self._player.set_media(media)
        media.release()

        with self._lock:
            self._frame = None

        self._path = path
        self._player.play()

    def go_to(self, place: float):
        if self._path is None:
            return

        state = self._player.get_state()

        if state in {self._vlc.State.Ended, self._vlc.State.Stopped}:
            self._player.play()

        self._player.set_position(min(max(place, 0.0), 0.99))

    def stop(self):
        if self._path is None:
            return

        self._player.stop()
        self._path = None

        with self._lock:
            self._frame = None

    def take_frame(self):
        with self._lock:
            frame, self._frame = self._frame, None

        return frame

    def _make_format_cb(self):
        @_VideoFormatCb
        def _cb(opaque, chroma, width, height, pitches, lines):
            ctypes.memmove(chroma, b"RV32", 4)

            frame_width, frame_height = preview_size(
                width[0], height[0], CLIP_PREVIEW_PX
            )
            if not frame_width:
                return 0

            width[0] = frame_width
            height[0] = frame_height
            pitches[0] = frame_width * 4
            lines[0] = frame_height

            self._buffer = ctypes.create_string_buffer(frame_width * frame_height * 4)
            self._size = (frame_width, frame_height)

            return 1

        return _cb

    def _on_lock(self, opaque, planes):
        planes[0] = ctypes.addressof(self._buffer)
        return None

    def _on_display(self, opaque, picture):
        width, height = self._size

        with self._lock:
            self._frame = (width, height, self._buffer.raw)
