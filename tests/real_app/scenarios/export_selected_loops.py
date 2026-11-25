"""Export Loops on a video while others are picked out: the loops of those
picked out exported, a file for each. One with only a start marker set
exported from it to the end, one with only an end marker set from the start
to it."""


def _at(d, cell, time):
    d.run(cell, "active", "seek", time)
    d.wait_until(lambda: abs(cell.time - time) < 400, f"at {time // 1000}s")


def _length(path):
    import subprocess

    said = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "csv=p=0",
            str(path),
        ],
        capture_output=True,
        text=True,
    ).stdout.strip()
    return float(said) if said else 0.0


def scenario(d):
    import os
    import shutil
    from pathlib import Path
    from unittest.mock import Mock

    from gridplayer.dialogs.export_loops import ExportAllOptions
    from gridplayer.player.managers import loop_export
    from gridplayer.utils.loop_export import (
        AllMode,
        ExportQuality,
        LoopOrder,
        OutputSize,
    )

    if shutil.which("ffmpeg") is None:
        d.note("no ffmpeg: nothing to export with")
        return

    clips = d.media.clips[:3]
    d.open(*clips)
    a, b, c = (d.wait_for_cell(clip.name) for clip in clips)
    for cell in (a, b, c):
        d.wait_until(lambda cell=cell: cell.is_playable, "plays")
        d.run(cell, "active", "set_pause", True)

    # a: only a start; b: only an end; c: a whole loop, not picked out
    _at(d, a, 17_000)
    d.act(a, "Set Loop Start")
    _at(d, b, 2_000)
    d.act(b, "Set Loop End")
    loops = b.video_params.loops
    d.check("b loops from the start", loops == [(0, 2000)], loops)
    _at(d, c, 5_000)
    d.act(c, "Set Loop Start")
    _at(d, c, 8_000)
    d.act(c, "Set Loop End")

    d.act(a, "Select")
    d.act(b, "Select")

    out = Path(os.environ["GP_USER_DATA_DIR"]).parent / "exported"
    shutil.rmtree(out, ignore_errors=True)
    told = Mock()
    loop_export.QCustomMessageBox.information = told
    asked = Mock(
        return_value=ExportAllOptions(
            mode=AllMode.EACH,
            folder=out,
            target=out / "all.mp4",
            size=OutputSize.LARGEST,
            fade_s=0.5,
            order=LoopOrder.TIMELINE,
            quality=ExportQuality.SMALL,
        )
    )
    loop_export.ExportAllLoopsDialog.ask = asked

    # from the one not picked out
    d.act(c, "Export Loops")
    d.wait_until(lambda: told.call_count == 1, "exported", timeout=60)

    d.check(
        "the two picked out offered",
        asked.call_args.kwargs["video_count"] == 2,
        asked.call_args.kwargs["video_count"],
    )
    made = sorted(path.name for path in out.iterdir())
    d.check(
        "a file for each picked out",
        made == ["a - loops.mp4", "b - loops.mp4"],
        made,
    )
    d.check(
        "a's from its start to the end",
        abs(_length(out / "a - loops.mp4") - 3.0) < 0.15,
        _length(out / "a - loops.mp4"),
    )
    d.check(
        "b's from the start to its end",
        abs(_length(out / "b - loops.mp4") - 2.0) < 0.15,
        _length(out / "b - loops.mp4"),
    )
