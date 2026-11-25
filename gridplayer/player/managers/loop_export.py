"""Export Loops: the active video's A-B loops made one video of their own
(or those of the videos picked out, as for all of them),
each fading into the next, by ffmpeg (see utils.loop_export), with how far
along it is shown and a way to stop it. And Export Loops of All Videos: the
loops of every video in the grid, or of those picked out, each video's into
a file of its own, or all of them into one.

ffmpeg is the one fetched for the player before, else the system's; on
Windows, where few have it, fetched once asked (see utils.ffmpeg_tool).
"""

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from PyQt5.QtCore import QProcess, Qt, QThread, pyqtSignal
from PyQt5.QtWidgets import QMessageBox, QProgressDialog

from gridplayer.dialogs.export_loops import ExportAllLoopsDialog, ExportLoopsDialog
from gridplayer.dialogs.messagebox import QCustomMessageBox
from gridplayer.player.managers.base import ManagerBase
from gridplayer.settings import Settings
from gridplayer.utils import ffmpeg_tool
from gridplayer.utils.app_dir import get_app_data_dir
from gridplayer.utils.loop_export import (
    AllMode,
    SourceInfo,
    SourceLoops,
    combined_command,
    combined_seconds,
    default_target,
    export_command,
    info_in,
    loop_count,
    output_seconds,
    probe_command,
    progress_of,
    segments_of,
    target_for_each,
)
from gridplayer.utils.qt import translate

# how long ffmpeg is given to say what is in a file
PROBE_TIMEOUT_MS = 15_000

# how much of what ffmpeg said last is shown when it fails
ERROR_TAIL_CHARS = 1500


# what the file of several videos' loops is called, beside the first
COMBINED_NAME = "All loops.mp4"


@dataclass(frozen=True)
class _Job:
    """One ffmpeg run of an export: what it makes, and how long that is."""

    command: list
    target: Path
    total_s: float


class _Fetcher(QThread):
    """ffmpeg fetched in a thread of its own, the window kept going."""

    progress = pyqtSignal(int, object)
    fetched = pyqtSignal(object)
    failed = pyqtSignal(str)
    cancelled = pyqtSignal()

    def __init__(self, data_dir: Path, parent=None):
        super().__init__(parent)

        self._data_dir = data_dir
        self._is_cancelled = False

    def cancel(self):
        self._is_cancelled = True

    def run(self):
        from streamlink import Streamlink

        from gridplayer.utils.network import apply_to_streamlink

        # the player's own network settings: its proxy, if it has one
        session = Streamlink()
        apply_to_streamlink(session)

        try:
            path = ffmpeg_tool.fetch_ffmpeg(
                self._data_dir,
                session.http,
                on_progress=lambda done, total: self.progress.emit(done, total),
                is_cancelled=lambda: self._is_cancelled,
            )
        except ffmpeg_tool.FetchCancelled:
            self.cancelled.emit()
        except Exception as e:
            self.failed.emit(str(e))
        else:
            self.fetched.emit(path)


class LoopExportManager(ManagerBase):
    error = pyqtSignal(str)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self._process: QProcess | None = None
        self._progress: QProgressDialog | None = None
        self._fetcher: _Fetcher | None = None

        # the exports to run one after another, the one running, and the
        # files made so far
        self._jobs: list[_Job] = []
        self._job_index = 0
        self._made: list[Path] = []

        self._output = ""
        self._errors = ""
        self._is_cancelled = False

        # what to do once ffmpeg is there, fetched or not
        self._then: Callable[[Path], None] | None = None

    @property
    def commands(self):
        return {
            "export_loops": self.cmd_export_loops,
            "is_active_loops_exportable": self.is_active_loops_exportable,
            "export_all_loops": self.cmd_export_all_loops,
            "is_any_loops_exportable": self.is_any_loops_exportable,
        }

    def is_active_loops_exportable(self) -> bool:
        return bool(self._picked_or_active()[0])

    def is_any_loops_exportable(self) -> bool:
        return bool(self._exportable_blocks()[0])

    @property
    def is_busy(self) -> bool:
        return self._process is not None or self._fetcher is not None

    # asked

    def cmd_export_loops(self):
        if self.is_busy:
            return

        videos, left_out = self._picked_or_active()

        if not videos:
            return

        # those picked out, as for all of them
        if len(videos) > 1 or left_out:
            self._with_ffmpeg(
                lambda ffmpeg: self._ask_and_export_all(ffmpeg, videos, left_out)
            )
            return

        source, loops = videos[0]

        self._with_ffmpeg(lambda ffmpeg: self._ask_and_export(ffmpeg, source, loops))

    def cmd_export_all_loops(self):
        if self.is_busy:
            return

        videos, left_out = self._exportable_blocks()

        if not videos:
            return

        self._with_ffmpeg(
            lambda ffmpeg: self._ask_and_export_all(ffmpeg, videos, left_out)
        )

    def _exportable_blocks(self) -> tuple[list[tuple[Path, list]], int]:
        """(file, loops) of each video to export, in the grid's order: those
        picked out, if any are, else all; and how many of them are left out,
        with no finished loop or not a file."""

        blocks = (
            self._ctx.commands.selected_cells()
            or self._ctx.video_blocks.blocks_for_ids(self._ctx.commands.layout_order())
        )

        return _with_loops(blocks)

    def _picked_or_active(self) -> tuple[list[tuple[Path, list]], int]:
        """As _exportable_blocks, of those picked out, or else of the active
        one."""

        blocks = self._ctx.commands.selected_cells()

        if not blocks:
            active = self._ctx.active_block
            blocks = [active] if active is not None else []

        return _with_loops(blocks)

    def _with_ffmpeg(self, then: Callable[[Path], None]):
        """then(ffmpeg) once there is one: found, or fetched once asked."""

        ffmpeg = ffmpeg_tool.find_ffmpeg(get_app_data_dir())

        if ffmpeg is not None:
            then(ffmpeg)
            return

        if not ffmpeg_tool.can_fetch():
            self.error.emit(
                translate(
                    "Export Loops",
                    "Exporting loops needs ffmpeg. Install it from your"
                    " system's packages, then try again.",
                )
            )
            return

        if self._is_fetching_wanted():
            self._then = then
            self._fetch()

    def _is_fetching_wanted(self) -> bool:
        answer = QCustomMessageBox.question(
            self.parent(),
            translate("Export Loops", "Export Loops"),
            translate(
                "Export Loops",
                "Exporting loops needs ffmpeg, which is downloaded once"
                " (about 100 MB) and kept with the player. Download it now?",
            ),
        )

        return answer == QMessageBox.Yes

    # ffmpeg fetched

    def _fetch(self):
        self._progress = self._progress_dialog(
            translate("Export Loops", "Downloading ffmpeg...")
        )

        fetcher = _Fetcher(get_app_data_dir(), self)
        fetcher.progress.connect(self._on_fetch_progress)
        fetcher.fetched.connect(self._on_fetched)
        fetcher.failed.connect(self._on_fetch_failed)
        fetcher.cancelled.connect(self._close_progress)
        fetcher.finished.connect(self._fetch_done)
        self._progress.canceled.connect(fetcher.cancel)

        self._fetcher = fetcher
        fetcher.start()

    def _on_fetch_progress(self, done: int, total):
        if self._progress is None:
            return

        if total:
            self._progress.setRange(0, 1000)
            self._progress.setValue(int(done * 1000 / total))
        else:
            self._progress.setRange(0, 0)

    def _on_fetched(self, path):
        self._close_progress()

        then, self._then = self._then, None
        if then is not None:
            then(Path(path))

    def _on_fetch_failed(self, message: str):
        self._close_progress()
        self._then = None
        self.error.emit(
            "{}\n\n{}".format(
                translate("Export Loops", "Couldn't download ffmpeg."), message
            )
        )

    def _fetch_done(self):
        if self._fetcher is not None:
            self._fetcher.deleteLater()
        self._fetcher = None

    # one video

    def _ask_and_export(self, ffmpeg: Path, source: Path, loops: list):
        settings = Settings()

        options = ExportLoopsDialog.ask(
            self.parent(),
            target=default_target(source),
            loop_count=loop_count(loops),
            fade_s=settings.get("export/loop_fade_s"),
            order=settings.get("export/loop_order"),
            quality=settings.get("export/loop_quality"),
        )

        if options is None:
            return

        _remember_common(options)

        if _is_over(options.target, [source]):
            return self._over_a_video()

        info = self._probe(ffmpeg, source)
        if info is None:
            return

        segments = segments_of(loops, options.order, info.length_ms)
        if not segments:
            return self._none_left()

        self._run(
            [
                _Job(
                    export_command(
                        ffmpeg,
                        source,
                        options.target,
                        segments,
                        options.fade_s,
                        info.has_audio,
                        options.quality,
                    ),
                    options.target,
                    output_seconds(segments, options.fade_s),
                )
            ]
        )

    # several videos

    def _ask_and_export_all(self, ffmpeg: Path, videos: list, left_out: int):
        settings = Settings()
        sources = [source for source, _ in videos]

        options = ExportAllLoopsDialog.ask(
            self.parent(),
            target=sources[0].parent / COMBINED_NAME,
            video_count=len(videos),
            loop_count=sum(loop_count(loops) for _, loops in videos),
            left_out=left_out,
            mode=settings.get("export/all_mode"),
            size=settings.get("export/all_size"),
            fade_s=settings.get("export/loop_fade_s"),
            order=settings.get("export/loop_order"),
            quality=settings.get("export/loop_quality"),
        )

        if options is None:
            return

        _remember_common(options)
        settings.set("export/all_mode", options.mode)
        settings.set("export/all_size", options.size)

        if options.mode == AllMode.EACH:
            targets = target_for_each(sources, options.folder)
        else:
            targets = [options.target]

        if any(_is_over(target, sources) for target in targets):
            return self._over_a_video()

        if options.folder is not None and options.mode == AllMode.EACH:
            options.folder.mkdir(parents=True, exist_ok=True)

        # each file asked about once
        infos = {}
        for source in dict.fromkeys(sources):
            info = self._probe(ffmpeg, source)
            if info is None:
                return
            infos[source] = info

        loops_of = [
            SourceLoops(
                source,
                segments_of(loops, options.order, infos[source].length_ms),
                infos[source],
            )
            for source, loops in videos
        ]

        # a loop to the end of a file ffmpeg gave no length of
        if not all(video.segments for video in loops_of):
            return self._none_left()

        if options.mode == AllMode.ONE:
            jobs = [
                _Job(
                    combined_command(
                        ffmpeg,
                        loops_of,
                        options.target,
                        options.fade_s,
                        options.size,
                        options.quality,
                    ),
                    options.target,
                    combined_seconds(loops_of, options.fade_s),
                )
            ]
        else:
            jobs = [
                _Job(
                    export_command(
                        ffmpeg,
                        video.source,
                        target,
                        video.segments,
                        options.fade_s,
                        video.info.has_audio,
                        options.quality,
                    ),
                    target,
                    output_seconds(video.segments, options.fade_s),
                )
                for video, target in zip(loops_of, targets)
            ]

        self._run(jobs)

    def _none_left(self):
        self.error.emit(translate("Export Loops", "Couldn't tell where a video ends."))

    def _over_a_video(self):
        self.error.emit(
            translate("Export Loops", "Can't export over the video itself.")
        )

    def _probe(self, ffmpeg: Path, source: Path) -> SourceInfo | None:
        """What is in the file: its sound, its size, its frame rate; None
        where ffmpeg could not be run at all, said so."""

        command = probe_command(ffmpeg, source)

        probe = QProcess(self)
        probe.start(command[0], command[1:])

        if not probe.waitForFinished(PROBE_TIMEOUT_MS):
            probe.kill()
            self.error.emit(translate("Export Loops", "Couldn't run ffmpeg."))
            return None

        said = bytes(probe.readAllStandardError()).decode("utf-8", "replace")

        return info_in(said)

    # run, one after another

    def _run(self, jobs: list[_Job]):
        self._jobs = jobs
        self._job_index = 0
        self._made = []
        self._is_cancelled = False

        self._progress = self._progress_dialog(
            translate("Export Loops", "Exporting loops...")
        )
        self._progress.setRange(0, 1000)
        self._progress.canceled.connect(self._cancel)

        self._start_job()

    @property
    def _job(self) -> _Job | None:
        if self._job_index < len(self._jobs):
            return self._jobs[self._job_index]
        return None

    def _start_job(self):
        self._output = ""
        self._errors = ""

        if len(self._jobs) > 1 and self._progress is not None:
            self._progress.setLabelText(
                translate(
                    "Export Loops", "Exporting loops... (video {NUMBER} of {COUNT})"
                ).format(NUMBER=self._job_index + 1, COUNT=len(self._jobs))
            )

        process = QProcess(self)
        process.readyReadStandardOutput.connect(self._on_output)
        process.readyReadStandardError.connect(self._on_errors)
        process.finished.connect(self._on_finished)
        process.errorOccurred.connect(self._on_process_error)

        self._process = process

        command = self._job.command
        process.start(command[0], command[1:])

    def _on_output(self):
        if self._process is None or self._job is None:
            return

        self._output += bytes(self._process.readAllStandardOutput()).decode(
            "utf-8", "replace"
        )
        # only the latest block of progress matters
        self._output = self._output[-4000:]

        done = progress_of(self._output, self._job.total_s)

        if done is not None and self._progress is not None:
            # the whole of them: those done, and how far this one is
            whole = (self._job_index + done) / len(self._jobs)
            self._progress.setValue(int(whole * 1000))

    def _on_errors(self):
        if self._process is None:
            return

        self._errors += bytes(self._process.readAllStandardError()).decode(
            "utf-8", "replace"
        )
        self._errors = self._errors[-ERROR_TAIL_CHARS * 2 :]

    def _cancel(self):
        if self._process is None:
            return

        self._is_cancelled = True
        self._process.kill()

    def _on_process_error(self, process_error):
        # one that could not start never finishes
        if process_error == QProcess.FailedToStart:
            self._done()
            self.error.emit(translate("Export Loops", "Couldn't run ffmpeg."))

    def _on_finished(self, exit_code, exit_status):
        job = self._job
        errors = self._errors
        is_done = exit_status == QProcess.NormalExit and exit_code == 0

        if self._process is not None:
            self._process.deleteLater()
        self._process = None

        if is_done and not self._is_cancelled:
            self._made.append(job.target)
            self._job_index += 1

            if self._job is not None:
                self._start_job()
                return

        # nothing half made left behind; those made before it kept
        if not is_done or self._is_cancelled:
            job.target.unlink(missing_ok=True)

        is_cancelled = self._is_cancelled
        made = list(self._made)

        self._done()

        if is_cancelled:
            return

        if not is_done:
            message = translate("Export Loops", "Couldn't export the loops.")
            if len(self._jobs) > 1:
                message += "\n" + translate(
                    "Export Loops", "Of {SOURCE}, after {COUNT} made."
                ).format(SOURCE=job.target.name, COUNT=len(made))
            self.error.emit(f"{message}\n\n{errors.strip()[-ERROR_TAIL_CHARS:]}")
            return

        QCustomMessageBox.information(
            self.parent(),
            translate("Export Loops", "Export Loops"),
            translate("Export Loops", "Loops exported to:"),
            info="\n".join(str(target) for target in made),
        )

    def _done(self):
        self._close_progress()

        if self._process is not None:
            self._process.deleteLater()

        self._process = None
        self._jobs = []
        self._job_index = 0

    # how far along

    def _progress_dialog(self, text: str) -> QProgressDialog:
        dialog = QProgressDialog(
            text, translate("Export Loops", "Cancel"), 0, 0, self.parent()
        )
        dialog.setWindowTitle(translate("Export Loops", "Export Loops"))
        dialog.setWindowModality(Qt.WindowModal)
        dialog.setMinimumDuration(0)
        dialog.setAutoClose(False)
        dialog.setAutoReset(False)
        dialog.setValue(0)
        dialog.show()
        return dialog

    def _close_progress(self):
        if self._progress is None:
            return

        progress, self._progress = self._progress, None

        # closing it is not cancelling
        progress.canceled.disconnect()
        progress.close()
        progress.deleteLater()

    def cleanup(self):
        if self._process is not None:
            self._cancel()
            self._process.waitForFinished(3000)

        if self._fetcher is not None:
            self._fetcher.cancel()
            self._fetcher.wait(3000)


def _with_loops(blocks) -> tuple[list[tuple[Path, list]], int]:
    videos = []
    for block in blocks:
        loops = _loops_of(block)
        if loops is not None:
            videos.append((Path(block.video_params.uri), loops))

    return videos, len(blocks) - len(videos)


def _loops_of(block) -> list | None:
    """A cell's loops to export, the one begun and not finished as well, to
    the end of the file: None for one with none, or not a file."""

    if block is None or not block.is_local_file or block.video_params is None:
        return None

    params = block.video_params
    loops = list(params.loops)

    begun = params.loop_start
    if begun is not None:
        loops.append((begun, None))

    return loops if loop_count(loops) else None


def _remember_common(options):
    settings = Settings()
    settings.set("export/loop_fade_s", float(options.fade_s))
    settings.set("export/loop_order", options.order)
    settings.set("export/loop_quality", options.quality)


def _is_over(target: Path, sources: list[Path]) -> bool:
    resolved = target.resolve()
    return any(resolved == source.resolve() for source in sources)
