"""Export Loops of All Videos: loops set on two videos, exported from the
all-videos menu, first into a file for each, then into one of them all;
each as long as its loops less the fades, with sound."""


def _loop(d, cell, start, end):
    d.run(cell, "active", "seek", start)
    d.wait_until(lambda: abs(cell.time - start) < 400, f"at {start // 1000}s")
    d.act(cell, "Set Loop Start")
    d.run(cell, "active", "seek", end)
    d.wait_until(lambda: abs(cell.time - end) < 400, f"at {end // 1000}s")
    d.act(cell, "Set Loop End")


def _probe(path):
    import subprocess

    said = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration:stream=codec_type",
            "-of",
            "csv=p=0",
            str(path),
        ],
        capture_output=True,
        text=True,
    ).stdout.split()
    return (float(said[-1]) if said else 0.0), said[:-1]


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

    a_clip, b_clip = d.media.clips[0], d.media.clips[1]
    d.open(a_clip, b_clip)
    a = d.wait_for_cell("a.mp4")
    b = d.wait_for_cell("b.mp4")
    for cell in (a, b):
        d.wait_until(lambda cell=cell: cell.is_playable, "plays")
        d.run(cell, "active", "set_pause", True)

    _loop(d, a, 2_000, 5_000)
    _loop(d, b, 9_000, 12_000)
    _loop(d, b, 14_000, 16_000)

    out = Path(os.environ["GP_USER_DATA_DIR"]).parent / "exported"
    shutil.rmtree(out, ignore_errors=True)
    told = Mock()
    loop_export.QCustomMessageBox.information = told

    def answered(**options):
        values = {
            "mode": AllMode.EACH,
            "folder": out,
            "target": out / "all.mp4",
            "size": OutputSize.LARGEST,
            "fade_s": 0.5,
            "order": LoopOrder.TIMELINE,
            "quality": ExportQuality.SMALL,
        }
        values.update(options)
        loop_export.ExportAllLoopsDialog.ask = Mock(
            return_value=ExportAllOptions(**values)
        )

    # a file for each
    answered()
    d.act(a, "Export Loops [ALL]")
    d.wait_until(lambda: told.call_count == 1, "each exported", timeout=60)

    length_a, streams_a = _probe(out / "a - loops.mp4")
    length_b, streams_b = _probe(out / "b - loops.mp4")
    d.check(
        "a's",
        abs(length_a - 3.0) < 0.15 and streams_a == ["video", "audio"],
        (length_a, streams_a),
    )
    d.check(
        "b's, faded",
        abs(length_b - 4.5) < 0.15 and streams_b == ["video", "audio"],
        (length_b, streams_b),
    )

    # one of them all
    answered(mode=AllMode.ONE)
    d.act(a, "Export Loops [ALL]")
    d.wait_until(lambda: told.call_count == 2, "all in one exported", timeout=60)

    length, streams = _probe(out / "all.mp4")
    # 3 + 3 + 2, two fades of 0.5 s
    d.check(
        "all in one",
        abs(length - 7.0) < 0.15 and streams == ["video", "audio"],
        (length, streams),
    )
