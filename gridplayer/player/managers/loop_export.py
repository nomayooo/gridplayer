"""Export Loops: the active video's A-B loops made one video of their own,
each fading into the next, by ffmpeg (see utils.loop_export), with how far
along it is shown and a way to stop it.

ffmpeg is the one fetched for the player before, else the system's; on
Windows, where few have it, fetched once asked (see utils.ffmpeg_tool).
"""

from pathlib import Path

from PyQt5.QtCore import QProcess, Qt, QThread, pyqtSignal
from PyQt5.QtWidgets import QMessageBox, QProgressDialog

from gridplayer.dialogs.export_loops import ExportLoopsDialog
from gridplayer.dialogs.messagebox import QCustomMessageBox
from gridplayer.player.managers.base import ManagerBase
from gridplayer.settings import Settings
from gridplayer.utils import ffmpeg_tool
from gridplayer.utils.app_dir import get_app_data_dir
from gridplayer.utils.loop_export import (
    default_target,
    export_command,
    has_audio_in,
    output_seconds,
    probe_command,
    progress_of,
    segments_of,
)
from gridplayer.utils.qt import translate

# how long ffmpeg is given to say what is in a file
PROBE_TIMEOUT_MS = 15_000

# how much of what ffmpeg said last is shown when it fails
ERROR_TAIL_CHARS = 1500


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

        self._target: Path | None = None
        self._total_s = 0.0
        self._output = ""
        self._errors = ""
        self._is_cancelled = False

    @property
    def commands(self):
        return {
            "export_loops": self.cmd_export_loops,
            "is_active_loops_exportable": self.is_active_loops_exportable,
        }

    def is_active_loops_exportable(self) -> bool:
        block = self._ctx.active_block

        if block is None or not block.is_local_file:
            return False

        return bool(segments_of(block.video_params.loops, _order()))

    @property
    def is_busy(self) -> bool:
        return self._process is not None or self._fetcher is not None

    # asked

    def cmd_export_loops(self):
        if self.is_busy:
            return

        block = self._ctx.active_block

        if block is None or not block.is_local_file:
            return

        self._source = Path(block.video_params.uri)
        self._loops = list(block.video_params.loops)

        if not segments_of(self._loops, _order()):
            return

        ffmpeg = ffmpeg_tool.find_ffmpeg(get_app_data_dir())

        if ffmpeg is not None:
            self._ask_and_export(ffmpeg)
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
        self._ask_and_export(Path(path))

    def _on_fetch_failed(self, message: str):
        self._close_progress()
        self.error.emit(
            "{}\n\n{}".format(
                translate("Export Loops", "Couldn't download ffmpeg."), message
            )
        )

    def _fetch_done(self):
        if self._fetcher is not None:
            self._fetcher.deleteLater()
        self._fetcher = None

    # exported

    def _ask_and_export(self, ffmpeg: Path):
        settings = Settings()

        options = ExportLoopsDialog.ask(
            self.parent(),
            target=default_target(self._source),
            loop_count=len(segments_of(self._loops, _order())),
            fade_s=settings.get("export/loop_fade_s"),
            order=settings.get("export/loop_order"),
            quality=settings.get("export/loop_quality"),
        )

        if options is None:
            return

        settings.set("export/loop_fade_s", float(options.fade_s))
        settings.set("export/loop_order", options.order)
        settings.set("export/loop_quality", options.quality)

        self._export(ffmpeg, options)

    def _export(self, ffmpeg: Path, options):
        segments = segments_of(self._loops, options.order)

        if options.target.resolve() == self._source.resolve():
            self.error.emit(
                translate("Export Loops", "Can't export over the video itself.")
            )
            return

        has_audio = self._has_audio(ffmpeg)
        if has_audio is None:
            return

        command = export_command(
            ffmpeg,
            self._source,
            options.target,
            segments,
            options.fade_s,
            has_audio,
            options.quality,
        )

        self._target = options.target
        self._total_s = output_seconds(segments, options.fade_s)
        self._output = ""
        self._errors = ""
        self._is_cancelled = False

        process = QProcess(self)
        process.readyReadStandardOutput.connect(self._on_output)
        process.readyReadStandardError.connect(self._on_errors)
        process.finished.connect(self._on_finished)
        process.errorOccurred.connect(self._on_process_error)

        self._progress = self._progress_dialog(
            translate("Export Loops", "Exporting loops...")
        )
        self._progress.setRange(0, 1000)
        self._progress.canceled.connect(self._cancel)

        self._process = process
        process.start(command[0], command[1:])

    def _has_audio(self, ffmpeg: Path) -> bool | None:
        """Whether the video has sound to fade too; None where ffmpeg could
        not be run at all, said so."""

        command = probe_command(ffmpeg, self._source)

        probe = QProcess(self)
        probe.start(command[0], command[1:])

        if not probe.waitForFinished(PROBE_TIMEOUT_MS):
            probe.kill()
            self.error.emit(translate("Export Loops", "Couldn't run ffmpeg."))
            return None

        said = bytes(probe.readAllStandardError()).decode("utf-8", "replace")

        return has_audio_in(said)

    def _on_output(self):
        if self._process is None:
            return

        self._output += bytes(self._process.readAllStandardOutput()).decode(
            "utf-8", "replace"
        )
        # only the latest block of progress matters
        self._output = self._output[-4000:]

        done = progress_of(self._output, self._total_s)

        if done is not None and self._progress is not None:
            self._progress.setValue(int(done * 1000))

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
        target = self._target
        is_cancelled = self._is_cancelled
        errors = self._errors

        self._done()

        is_done = exit_status == QProcess.NormalExit and exit_code == 0

        if is_cancelled or not is_done:
            # nothing half made left behind
            if target is not None:
                target.unlink(missing_ok=True)

        if is_cancelled:
            return

        if not is_done:
            self.error.emit(
                "{}\n\n{}".format(
                    translate("Export Loops", "Couldn't export the loops."),
                    errors.strip()[-ERROR_TAIL_CHARS:],
                )
            )
            return

        QCustomMessageBox.information(
            self.parent(),
            translate("Export Loops", "Export Loops"),
            translate("Export Loops", "Loops exported to:"),
            info=str(target),
        )

    def _done(self):
        self._close_progress()

        if self._process is not None:
            self._process.deleteLater()

        self._process = None
        self._target = None

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


def _order():
    return Settings().get("export/loop_order")
