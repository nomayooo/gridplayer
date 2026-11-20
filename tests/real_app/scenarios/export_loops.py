"""Export Loops: two A-B loops set on a video, exported from its menu with
a fade between them; the video made is as long as the two less the fade,
with its sound, and said where it is."""


def _loop(d, a, start, end):
    d.run(a, "active", "seek", start)
    d.wait_until(lambda: abs(a.time - start) < 400, f"at {start // 1000}s")
    d.act(a, "Set Loop Start")
    d.run(a, "active", "seek", end)
    d.wait_until(lambda: abs(a.time - end) < 400, f"at {end // 1000}s")
    d.act(a, "Set Loop End")


def scenario(d):
    import os
    import shutil
    import subprocess
    from pathlib import Path
    from unittest.mock import Mock

    from gridplayer.dialogs.export_loops import ExportOptions
    from gridplayer.player.managers import loop_export
    from gridplayer.utils.loop_export import ExportQuality, LoopOrder

    if shutil.which("ffmpeg") is None:
        d.note("no ffmpeg: nothing to export with")
        return

    clip = d.media.clips[1]  # b.mp4, with sound
    d.open(clip)
    a = d.wait_for_cell("b.mp4")
    d.wait_until(lambda: a.is_playable, "plays")
    d.run(a, "active", "set_pause", True)
    d.ctx.active_block = a

    _loop(d, a, 2_000, 5_000)
    _loop(d, a, 9_000, 12_000)
    d.check("two loops", len(a.video_params.loops) == 2, a.video_params.loops)

    target = Path(os.environ["GP_USER_DATA_DIR"]).parent / "loops.mp4"
    target.unlink(missing_ok=True)

    loop_export.ExportLoopsDialog.ask = Mock(
        return_value=ExportOptions(target, 0.5, LoopOrder.TIMELINE, ExportQuality.SMALL)
    )
    told = Mock()
    loop_export.QCustomMessageBox.information = told

    d.act(a, "Export Loops")
    d.wait_until(lambda: told.called, "exported", timeout=60)

    said = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration:stream=codec_type",
            "-of",
            "csv=p=0",
            str(target),
        ],
        capture_output=True,
        text=True,
    ).stdout.split()
    length = float(said[-1])

    d.check("as long as the two less the fade", abs(length - 5.5) < 0.15, said)
    d.check("with its sound", said[:-1] == ["video", "audio"], said)
    d.check("said where", told.call_args.kwargs.get("info") == str(target))
