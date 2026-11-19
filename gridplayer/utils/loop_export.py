"""A video's A-B loops cut out of it and joined into one video of their own,
one after another, each fading into the next: the ffmpeg command for it,
and how far along it is from what ffmpeg says.

Pure: nothing run here (see player.managers.loop_export).
"""

from dataclasses import dataclass
from enum import Enum
from pathlib import Path

# a fade no longer than this share of the shortest loop, for each to show
# some of itself whole
FADE_SHARE_MAX = 0.5


class LoopOrder(Enum):
    """The loops one after another as they come in the video, or as they
    were made, as Next Loop goes round them."""

    TIMELINE = "timeline"
    MADE = "made"


class ExportQuality(Enum):
    HIGH = "high"
    MEDIUM = "medium"
    SMALL = "small"


# x264's constant quality for each: lower is better, and bigger
_CRF = {ExportQuality.HIGH: 18, ExportQuality.MEDIUM: 22, ExportQuality.SMALL: 27}
_AUDIO_BITRATE = {
    ExportQuality.HIGH: "192k",
    ExportQuality.MEDIUM: "160k",
    ExportQuality.SMALL: "128k",
}


@dataclass(frozen=True)
class Segment:
    start_ms: int
    end_ms: int

    @property
    def seconds(self) -> float:
        return (self.end_ms - self.start_ms) / 1000


def segments_of(loops, order: LoopOrder) -> list[Segment]:
    """The loops to export, finished ones only (a loop begun has no end),
    in the order asked."""

    segments = [
        Segment(start, end) for start, end in loops if end is not None and end > start
    ]

    if order == LoopOrder.TIMELINE:
        segments.sort(key=lambda s: (s.start_ms, s.end_ms))

    return segments


def fade_for(segments: list[Segment], fade_s: float) -> float:
    """The fade made to fit: none for one loop, never longer than a share
    of the shortest."""

    if len(segments) < 2 or fade_s <= 0:
        return 0.0

    shortest = min(segment.seconds for segment in segments)

    return round(min(fade_s, shortest * FADE_SHARE_MAX), 3)


def output_seconds(segments: list[Segment], fade_s: float) -> float:
    """How long the video made is: each fade overlaps two loops."""

    fade = fade_for(segments, fade_s)

    return sum(segment.seconds for segment in segments) - fade * (len(segments) - 1)


def _s(ms: int) -> str:
    return f"{ms / 1000:.3f}"


def filter_graph(segments: list[Segment], fade_s: float, has_audio: bool) -> str:
    """Each loop, an input of its own (see export_command), started at 0;
    then each joined to what came before it with a crossfade (xfade,
    acrossfade), or simply one after another (concat) with no fade."""

    fade = fade_for(segments, fade_s)
    parts = []

    for i in range(len(segments)):
        parts.append(f"[{i}:v:0]setpts=PTS-STARTPTS[v{i}]")
        if has_audio:
            parts.append(f"[{i}:a:0]asetpts=PTS-STARTPTS[a{i}]")

    count = len(segments)

    if count == 1:
        parts.append("[v0]null[vout]")
        if has_audio:
            parts.append("[a0]anull[aout]")
        return ";".join(parts)

    if fade == 0:
        inputs = "".join(
            f"[v{i}][a{i}]" if has_audio else f"[v{i}]" for i in range(count)
        )
        outputs = "[vout][aout]" if has_audio else "[vout]"
        parts.append(f"{inputs}concat=n={count}:v=1:a={1 if has_audio else 0}{outputs}")
        return ";".join(parts)

    # what has been joined so far, and how long it is
    video, audio = "v0", "a0"
    length = segments[0].seconds

    for i in range(1, count):
        is_last = i == count - 1
        video_out = "vout" if is_last else f"vx{i}"
        offset = length - fade

        parts.append(
            f"[{video}][v{i}]xfade=transition=fade:duration={fade:.3f}"
            f":offset={offset:.3f}[{video_out}]"
        )

        if has_audio:
            audio_out = "aout" if is_last else f"ax{i}"
            parts.append(f"[{audio}][a{i}]acrossfade=d={fade:.3f}[{audio_out}]")
            audio = audio_out

        video = video_out
        length += segments[i].seconds - fade

    return ";".join(parts)


def export_command(
    ffmpeg: Path,
    source: Path,
    target: Path,
    segments: list[Segment],
    fade_s: float,
    has_audio: bool,
    quality: ExportQuality = ExportQuality.HIGH,
) -> list[str]:
    """The program and its arguments, as a list, for QProcess or subprocess;
    progress written to its standard output (see progress_of)."""

    graph = filter_graph(segments, fade_s, has_audio)

    command = [str(ffmpeg), "-hide_banner", "-nostdin", "-y"]

    # each loop the file opened again where it starts, for just as long:
    # ffmpeg seeks there rather than reading all before it, and the loops
    # come in any order
    for segment in segments:
        command += [
            "-ss",
            _s(segment.start_ms),
            "-t",
            f"{segment.seconds:.3f}",
            "-i",
            str(source),
        ]

    command += ["-filter_complex", graph, "-map", "[vout]"]

    # the loops alone: not the file's chapters, which no longer fit
    command += ["-map_chapters", "-1"]

    if has_audio:
        command += ["-map", "[aout]"]

    command += [
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-crf",
        str(_CRF[quality]),
        "-pix_fmt",
        "yuv420p",
    ]

    if has_audio:
        command += ["-c:a", "aac", "-b:a", _AUDIO_BITRATE[quality]]

    command += [
        "-movflags",
        "+faststart",
        "-progress",
        "pipe:1",
        "-nostats",
        str(target),
    ]

    return command


def probe_command(ffmpeg: Path, source: Path) -> list[str]:
    """ffmpeg asked only what is in the file: it says so on its error
    output, and stops for want of an output."""

    return [str(ffmpeg), "-hide_banner", "-nostdin", "-i", str(source)]


def has_audio_in(probe_output: str) -> bool:
    return any(
        "Stream #" in line and ": Audio:" in line for line in probe_output.splitlines()
    )


def progress_of(progress_text: str, total_s: float) -> float | None:
    """How far along, 0 to 1, from the last out_time ffmpeg wrote in its
    -progress output; None for none yet."""

    seconds = None

    for line in progress_text.splitlines():
        key, _, value = line.partition("=")

        if key == "out_time_us" and value.strip().lstrip("-").isdigit():
            seconds = int(value) / 1_000_000

    if seconds is None or total_s <= 0:
        return None

    return max(0.0, min(1.0, seconds / total_s))


def default_target(source: Path) -> Path:
    """Beside the video, named after it."""

    return source.with_name(f"{source.stem} - loops.mp4")
