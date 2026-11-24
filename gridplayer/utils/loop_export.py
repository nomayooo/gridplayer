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


class AllMode(Enum):
    """Several videos' loops: a file for each, or all of them in one."""

    EACH = "each"
    ONE = "one"


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

    return ";".join(parts + _joined(segments, fade, has_audio))


def _joined(segments: list[Segment], fade: float, has_audio: bool) -> list[str]:
    """The clips ready as [v0], [a0], [v1]... joined into [vout] (and
    [aout]): each crossfading into the next, or one after another."""

    parts = []
    count = len(segments)

    if count == 1:
        parts.append("[v0]null[vout]")
        if has_audio:
            parts.append("[a0]anull[aout]")
        return parts

    if fade == 0:
        inputs = "".join(
            f"[v{i}][a{i}]" if has_audio else f"[v{i}]" for i in range(count)
        )
        outputs = "[vout][aout]" if has_audio else "[vout]"
        parts.append(f"{inputs}concat=n={count}:v=1:a={1 if has_audio else 0}{outputs}")
        return parts

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

    return parts


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

    return _command(
        ffmpeg,
        [(source, segment) for segment in segments],
        filter_graph(segments, fade_s, has_audio),
        target,
        has_audio,
        quality,
    )


def _command(ffmpeg, clips, graph: str, target, has_audio: bool, quality):
    command = [str(ffmpeg), "-hide_banner", "-nostdin", "-y"]

    # each loop the file opened again where it starts, for just as long:
    # ffmpeg seeks there rather than reading all before it, and the loops
    # come in any order
    for source, segment in clips:
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


# several videos' loops made one video: each made the same size, its shape
# kept within it on black, at one frame rate, and its sound at one rate and
# in stereo, silence for one without, for them to be joined
AUDIO_RATE = 48000
DEFAULT_FPS = 30
MAX_FPS = 60


class OutputSize(Enum):
    """How big a video of several is made: as the biggest of them, or as
    a 1080p or 720p frame."""

    LARGEST = "largest"
    P1080 = "1080p"
    P720 = "720p"


_FRAMES = {OutputSize.P1080: (1920, 1080), OutputSize.P720: (1280, 720)}


@dataclass(frozen=True)
class SourceInfo:
    """What ffmpeg says of a file: its picture's size and frame rate, None
    where it does not say, and whether it has sound."""

    has_audio: bool
    size: tuple[int, int] | None = None
    fps: float | None = None


@dataclass(frozen=True)
class SourceLoops:
    source: Path
    segments: list[Segment]
    info: SourceInfo


def info_in(probe_output: str) -> SourceInfo:
    import re

    size = fps = None

    for line in probe_output.splitlines():
        if "Stream #" not in line or ": Video:" not in line:
            continue

        found = re.search(r"\b(\d{2,5})x(\d{2,5})\b", line)
        if found and size is None:
            size = (int(found.group(1)), int(found.group(2)))

        found = re.search(r"([\d.]+) fps", line)
        if found and fps is None:
            fps = float(found.group(1))

    return SourceInfo(has_audio=has_audio_in(probe_output), size=size, fps=fps)


def frame_of(videos: list[SourceLoops], size: OutputSize) -> tuple[int, int]:
    """The frame the clips are put in: even, for the encoder."""

    if size in _FRAMES:
        return _FRAMES[size]

    sizes = [video.info.size for video in videos if video.info.size]
    if not sizes:
        return _FRAMES[OutputSize.P1080]

    width, height = max(sizes, key=lambda wh: wh[0] * wh[1])

    return width - width % 2, height - height % 2


def fps_of(videos: list[SourceLoops]) -> float:
    rates = [video.info.fps for video in videos if video.info.fps]

    return min(max(rates), MAX_FPS) if rates else DEFAULT_FPS


def combined_clips(videos: list[SourceLoops]) -> list[tuple[Path, Segment, bool]]:
    """Each clip to join, one after another: the videos in turn, the loops
    of each in their order."""

    return [
        (video.source, segment, video.info.has_audio)
        for video in videos
        for segment in video.segments
    ]


def combined_graph(
    videos: list[SourceLoops], fade_s: float, size: OutputSize
) -> tuple[str, bool]:
    """The filter graph joining every video's loops, and whether it has
    sound: any of them with sound, every clip has, silence where its video
    has none, for each to fade into the next."""

    clips = combined_clips(videos)
    segments = [segment for _, segment, _ in clips]
    fade = fade_for(segments, fade_s)
    width, height = frame_of(videos, size)
    fps = fps_of(videos)
    has_audio = any(has for _, _, has in clips)

    parts = []

    for i, (_source, segment, clip_has_audio) in enumerate(clips):
        parts.append(
            f"[{i}:v:0]scale={width}:{height}:force_original_aspect_ratio=decrease,"
            f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:color=black,setsar=1,"
            f"fps={fps:g},format=yuv420p,setpts=PTS-STARTPTS[v{i}]"
        )

        if not has_audio:
            continue

        if clip_has_audio:
            parts.append(
                f"[{i}:a:0]aformat=sample_fmts=fltp:sample_rates={AUDIO_RATE}"
                f":channel_layouts=stereo,asetpts=PTS-STARTPTS[a{i}]"
            )
        else:
            parts.append(
                f"anullsrc=channel_layout=stereo:sample_rate={AUDIO_RATE},"
                f"atrim=duration={segment.seconds:.3f},"
                f"aformat=sample_fmts=fltp,asetpts=PTS-STARTPTS[a{i}]"
            )

    return ";".join(parts + _joined(segments, fade, has_audio)), has_audio


def combined_command(
    ffmpeg: Path,
    videos: list[SourceLoops],
    target: Path,
    fade_s: float,
    size: OutputSize = OutputSize.LARGEST,
    quality: ExportQuality = ExportQuality.HIGH,
) -> list[str]:
    """Every video's loops made one video, each fading into the next."""

    graph, has_audio = combined_graph(videos, fade_s, size)
    clips = [(source, segment) for source, segment, _ in combined_clips(videos)]

    return _command(ffmpeg, clips, graph, target, has_audio, quality)


def combined_seconds(videos: list[SourceLoops], fade_s: float) -> float:
    segments = [segment for _, segment, _ in combined_clips(videos)]

    return output_seconds(segments, fade_s)


def target_for_each(sources: list[Path], folder: Path | None) -> list[Path]:
    """Where each video's loops go: beside it, or in the folder given; a
    second of one name, as the same file in two cells, numbered."""

    taken: set[Path] = set()
    targets = []

    for source in sources:
        target = default_target(source)
        if folder is not None:
            target = folder / target.name

        number = 2
        stem = target.stem
        while target in taken:
            target = target.with_name(f"{stem} ({number}).mp4")
            number += 1

        taken.add(target)
        targets.append(target)

    return targets
