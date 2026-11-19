"""Export Loops: a video's A-B loops made one video, each fading into the
next. The ffmpeg command for it; ffmpeg found, or fetched on Windows; and
the export itself, run with the real ffmpeg where there is one."""

import hashlib
import io
import shutil
import subprocess
import time
import zipfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from PyQt5.QtWidgets import QApplication, QMessageBox

from gridplayer.dialogs.export_loops import ExportLoopsDialog, ExportOptions
from gridplayer.player.managers import loop_export as manager_module
from gridplayer.player.managers.loop_export import LoopExportManager
from gridplayer.utils import ffmpeg_tool
from gridplayer.utils.loop_export import (
    ExportQuality,
    LoopOrder,
    Segment,
    default_target,
    export_command,
    fade_for,
    filter_graph,
    has_audio_in,
    output_seconds,
    progress_of,
    segments_of,
)
from tests.conftest import StoredSettings

LOOPS = [(9000, 12000), (2000, 5000), (14000, None), (14000, 17500)]

FFMPEG = shutil.which("ffmpeg")
needs_ffmpeg = pytest.mark.skipif(FFMPEG is None, reason="no ffmpeg here")


class TestTheLoops:
    def test_finished_ones_only_as_they_come_in_the_video(self):
        assert segments_of(LOOPS, LoopOrder.TIMELINE) == [
            Segment(2000, 5000),
            Segment(9000, 12000),
            Segment(14000, 17500),
        ]

    def test_or_as_they_were_made(self):
        assert segments_of(LOOPS, LoopOrder.MADE) == [
            Segment(9000, 12000),
            Segment(2000, 5000),
            Segment(14000, 17500),
        ]

    def test_one_with_no_length_left_out(self):
        assert segments_of([(5000, 5000)], LoopOrder.TIMELINE) == []


class TestTheFade:
    def test_as_asked(self):
        assert fade_for([Segment(0, 3000), Segment(5000, 8000)], 0.5) == 0.5

    def test_none_for_one_loop(self):
        assert fade_for([Segment(0, 3000)], 0.5) == 0

    def test_no_longer_than_half_the_shortest(self):
        assert fade_for([Segment(0, 400), Segment(5000, 8000)], 2.0) == 0.2

    def test_the_length_made_each_fade_overlapping_two(self):
        segments = [Segment(0, 3000), Segment(5000, 8000), Segment(9000, 11500)]

        assert output_seconds(segments, 0.5) == pytest.approx(8.5 - 1.0)
        assert output_seconds(segments, 0) == pytest.approx(8.5)


class TestTheCommand:
    SEGMENTS = (Segment(2000, 5000), Segment(9000, 12000), Segment(14000, 17500))

    def test_each_loop_opened_where_it_starts_for_as_long(self):
        command = export_command(
            Path("ffmpeg"),
            Path("in.mp4"),
            Path("out.mp4"),
            list(self.SEGMENTS),
            0.5,
            True,
        )

        starts = [command[i + 1] for i, a in enumerate(command) if a == "-ss"]
        lengths = [command[i + 1] for i, a in enumerate(command) if a == "-t"]
        assert starts == ["2.000", "9.000", "14.000"]
        assert lengths == ["3.000", "3.000", "3.500"]
        assert command.count("-i") == 3
        assert command[-1] == "out.mp4"

    def test_crossfaded_at_each_join(self):
        graph = filter_graph(list(self.SEGMENTS), 0.5, has_audio=True)

        assert "xfade=transition=fade:duration=0.500:offset=2.500[vx1]" in graph
        # 3 + 3 - 0.5 so far, the next fade half a second before its end
        assert "xfade=transition=fade:duration=0.500:offset=5.000[vout]" in graph
        assert graph.count("acrossfade=d=0.500") == 2
        assert "[aout]" in graph

    def test_without_sound_none_faded(self):
        graph = filter_graph(list(self.SEGMENTS), 0.5, has_audio=False)
        command = export_command(
            Path("ffmpeg"), Path("i"), Path("o"), list(self.SEGMENTS), 0.5, False
        )

        assert "acrossfade" not in graph
        assert "[aout]" not in command

    def test_no_fade_one_after_another(self):
        graph = filter_graph(list(self.SEGMENTS), 0, has_audio=True)

        assert "xfade" not in graph
        assert "concat=n=3:v=1:a=1[vout][aout]" in graph

    def test_one_loop_alone(self):
        graph = filter_graph([self.SEGMENTS[0]], 0.5, has_audio=True)

        assert "xfade" not in graph
        assert "[v0]null[vout]" in graph

    @pytest.mark.parametrize(
        ("quality", "crf"),
        [
            (ExportQuality.HIGH, "18"),
            (ExportQuality.MEDIUM, "22"),
            (ExportQuality.SMALL, "27"),
        ],
    )
    def test_quality(self, quality, crf):
        command = export_command(
            Path("f"), Path("i"), Path("o"), list(self.SEGMENTS), 0.5, True, quality
        )

        assert command[command.index("-crf") + 1] == crf

    def test_progress_said_on_its_output(self):
        command = export_command(
            Path("f"), Path("i"), Path("o"), list(self.SEGMENTS), 0.5, True
        )

        assert command[command.index("-progress") + 1] == "pipe:1"


class TestWhatFfmpegSays:
    def test_sound_in_it(self):
        said = (
            "  Stream #0:0[0x1](und): Video: h264\n"
            "  Stream #0:1[0x2](eng): Audio: aac (LC), 48000 Hz, stereo\n"
        )

        assert has_audio_in(said)
        assert not has_audio_in("  Stream #0:0: Video: h264\n")

    def test_how_far_along(self):
        said = "out_time_us=1000000\nprogress=continue\nout_time_us=3000000\n"

        assert progress_of(said, 6.0) == pytest.approx(0.5)
        assert progress_of("progress=continue\n", 6.0) is None
        assert progress_of("out_time_us=99000000\n", 6.0) == 1.0
        assert progress_of("out_time_us=-5\n", 6.0) == 0.0

    def test_saved_beside_the_video(self, tmp_path):
        assert default_target(tmp_path / "Film.mkv") == tmp_path / "Film - loops.mp4"


def _media(name):
    found = sorted(Path("build/test-media").glob(f"*/**/{name}"))
    if not found:
        pytest.skip("no test media: built by the real-app tests")
    return found[0].resolve()


def _probe(path: Path) -> tuple[float, list[str]]:
    said = subprocess.run(
        [
            str(Path(FFMPEG).with_name("ffprobe")),
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
        check=True,
    ).stdout.split()
    return float(said[-1]), said[:-1]


@needs_ffmpeg
class TestMadeByFfmpeg:
    """The command run with the real ffmpeg: the video it makes as long as
    reckoned, with sound where the video has it."""

    @pytest.mark.parametrize("order", [LoopOrder.TIMELINE, LoopOrder.MADE])
    def test_loops_faded_one_into_the_next(self, tmp_path, order):
        source = _media("b.mp4")
        segments = segments_of([(9000, 12000), (2000, 5000)], order)
        target = tmp_path / "out.mp4"

        subprocess.run(
            export_command(Path(FFMPEG), source, target, segments, 0.5, True),
            capture_output=True,
            check=True,
        )

        length, streams = _probe(target)
        assert length == pytest.approx(output_seconds(segments, 0.5), abs=0.1)
        assert streams == ["video", "audio"]

    def test_one_without_sound(self, tmp_path):
        source = _media("square.mp4")
        segments = segments_of([(1000, 3000), (5000, 8000)], LoopOrder.TIMELINE)
        target = tmp_path / "out.mp4"

        subprocess.run(
            export_command(Path(FFMPEG), source, target, segments, 0.5, False),
            capture_output=True,
            check=True,
        )

        length, streams = _probe(target)
        assert length == pytest.approx(4.5, abs=0.1)
        assert streams == ["video"]


class TestFindingFfmpeg:
    def test_the_one_fetched_before_first(self, tmp_path, monkeypatch):
        fetched = ffmpeg_tool.fetched_path(tmp_path)
        fetched.parent.mkdir()
        fetched.write_bytes(b"x")
        monkeypatch.setattr(
            ffmpeg_tool.shutil, "which", lambda _name: "/usr/bin/ffmpeg"
        )

        assert ffmpeg_tool.find_ffmpeg(tmp_path) == fetched

    def test_else_the_systems(self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            ffmpeg_tool.shutil, "which", lambda _name: "/usr/bin/ffmpeg"
        )

        assert ffmpeg_tool.find_ffmpeg(tmp_path) == Path("/usr/bin/ffmpeg")

    def test_none(self, tmp_path, monkeypatch):
        monkeypatch.setattr(ffmpeg_tool.shutil, "which", lambda _name: None)

        assert ffmpeg_tool.find_ffmpeg(tmp_path) is None

    def test_fetched_on_windows_only(self, monkeypatch):
        monkeypatch.setattr(ffmpeg_tool.env, "IS_WINDOWS", True)
        assert ffmpeg_tool.can_fetch()

        monkeypatch.setattr(ffmpeg_tool.env, "IS_WINDOWS", False)
        assert not ffmpeg_tool.can_fetch()


def _zip_of(exe_name: str, content: bytes = b"MZ fake ffmpeg") -> bytes:
    data = io.BytesIO()
    with zipfile.ZipFile(data, "w") as archive:
        archive.writestr("ffmpeg-7.1-essentials_build/README.txt", "read me")
        archive.writestr(f"ffmpeg-7.1-essentials_build/bin/{exe_name}", content)
        archive.writestr("ffmpeg-7.1-essentials_build/bin/ffprobe.exe", b"probe")
    return data.getvalue()


class _Response:
    def __init__(self, body: bytes, status=200):
        self.content = body
        self.text = body.decode("utf-8", "replace")
        self.status_code = status
        self.headers = {"Content-Length": str(len(body))}

    def raise_for_status(self):
        if self.status_code >= 400:
            raise OSError(f"HTTP {self.status_code}")

    def iter_content(self, size):
        for i in range(0, len(self.content), size):
            yield self.content[i : i + size]

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False


class _Session:
    """A web of a few pages: the responses by address."""

    def __init__(self, pages):
        self.pages = pages
        self.asked = []

    def get(self, url, **_kwargs):
        self.asked.append(url)
        page = self.pages.get(url)
        if page is None:
            return _Response(b"not found", 404)
        return _Response(page)


SOURCE = ffmpeg_tool.Source("https://one/ff.zip", "https://one/ff.zip.sha256")
OTHER = ffmpeg_tool.Source("https://two/build.zip", "https://two/checksums.sha256")


class TestFetching:
    @pytest.fixture(autouse=True)
    def _on_windows(self, monkeypatch):
        monkeypatch.setattr(ffmpeg_tool.env, "IS_WINDOWS", True)

    def test_fetched_checked_and_kept(self, tmp_path):
        zipped = _zip_of("ffmpeg.exe")
        session = _Session(
            {
                SOURCE.zip_url: zipped,
                SOURCE.sha256_url: hashlib.sha256(zipped).hexdigest().encode(),
            }
        )
        progress = []

        path = ffmpeg_tool.fetch_ffmpeg(
            tmp_path,
            session,
            on_progress=lambda done, total: progress.append((done, total)),
            sources=(SOURCE,),
        )

        assert path == tmp_path / "ffmpeg" / "ffmpeg.exe"
        assert path.read_bytes() == b"MZ fake ffmpeg"
        assert progress[-1] == (len(zipped), len(zipped))
        # nothing else left there
        assert [p.name for p in path.parent.iterdir()] == ["ffmpeg.exe"]

    def test_a_checksum_among_others_by_its_name(self, tmp_path):
        zipped = _zip_of("ffmpeg.exe")
        sums = (
            f"{'0' * 64}  something-else.zip\n"
            f"{hashlib.sha256(zipped).hexdigest()}  build.zip\n"
        )
        session = _Session({OTHER.zip_url: zipped, OTHER.sha256_url: sums.encode()})

        path = ffmpeg_tool.fetch_ffmpeg(tmp_path, session, sources=(OTHER,))

        assert path.is_file()

    def test_a_wrong_checksum_not_kept_the_next_tried(self, tmp_path):
        zipped = _zip_of("ffmpeg.exe")
        session = _Session(
            {
                SOURCE.zip_url: zipped,
                SOURCE.sha256_url: b"f" * 64,
                OTHER.zip_url: zipped,
                OTHER.sha256_url: f"{hashlib.sha256(zipped).hexdigest()}  build.zip".encode(),
            }
        )

        path = ffmpeg_tool.fetch_ffmpeg(tmp_path, session, sources=(SOURCE, OTHER))

        assert session.asked[-1] == OTHER.zip_url
        assert path.is_file()

    def test_none_to_be_had_said(self, tmp_path):
        with pytest.raises(ffmpeg_tool.FetchFailed):
            ffmpeg_tool.fetch_ffmpeg(tmp_path, _Session({}), sources=(SOURCE, OTHER))

        assert not ffmpeg_tool.fetched_path(tmp_path).exists()

    def test_cancelled_nothing_kept(self, tmp_path):
        zipped = _zip_of("ffmpeg.exe")
        session = _Session(
            {
                SOURCE.zip_url: zipped,
                SOURCE.sha256_url: hashlib.sha256(zipped).hexdigest().encode(),
            }
        )

        with pytest.raises(ffmpeg_tool.FetchCancelled):
            ffmpeg_tool.fetch_ffmpeg(
                tmp_path,
                session,
                on_progress=lambda *_: None,
                is_cancelled=lambda: bool(session.asked[1:]),
                sources=(SOURCE,),
            )

        assert list((tmp_path / "ffmpeg").iterdir()) == []

    def test_a_zip_without_it(self, tmp_path):
        zipped = _zip_of("something.exe")
        session = _Session(
            {
                SOURCE.zip_url: zipped,
                SOURCE.sha256_url: hashlib.sha256(zipped).hexdigest().encode(),
            }
        )

        with pytest.raises(ffmpeg_tool.FetchFailed):
            ffmpeg_tool.fetch_ffmpeg(tmp_path, session, sources=(SOURCE,))


class TestTheWindow:
    def _dialog(self, tmp_path, **kwargs):
        values = {
            "target": tmp_path / "Film - loops.mp4",
            "loop_count": 3,
            "fade_s": 0.5,
            "order": LoopOrder.MADE,
            "quality": ExportQuality.MEDIUM,
        }
        values.update(kwargs)
        return ExportLoopsDialog(**values)

    def test_as_it_was_last(self, tmp_path):
        options = self._dialog(tmp_path).options()

        assert options == ExportOptions(
            target=tmp_path / "Film - loops.mp4",
            fade_s=0.5,
            order=LoopOrder.MADE,
            quality=ExportQuality.MEDIUM,
        )

    def test_an_mp4_whatever_its_name(self, tmp_path):
        dialog = self._dialog(tmp_path)
        dialog.target.setText(str(tmp_path / "clip"))

        assert dialog.options().target == tmp_path / "clip.mp4"

    def test_no_name_no_export(self, tmp_path):
        dialog = self._dialog(tmp_path)
        dialog.target.setText("  ")

        assert not dialog.ok_button.isEnabled()

    def test_how_many_said(self, tmp_path):
        assert "3" in self._dialog(tmp_path).count_note.text()

    def test_no_fade_said_so(self, tmp_path):
        dialog = self._dialog(tmp_path, fade_s=0.0)

        assert dialog.fade.text() == "No fade"


# the export run by the manager


@pytest.fixture
def stored(monkeypatch):
    stored = StoredSettings()
    monkeypatch.setattr(manager_module, "Settings", lambda: stored)
    return stored


def _block(uri, loops):
    return SimpleNamespace(
        is_local_file=isinstance(uri, Path),
        video_params=SimpleNamespace(uri=uri, loops=list(loops)),
    )


def _manager(block, monkeypatch, tmp_path):
    monkeypatch.setattr(manager_module, "get_app_data_dir", lambda: tmp_path / "data")
    manager = LoopExportManager(context=SimpleNamespace(active_block=block))
    manager.errors = []
    manager.error.connect(manager.errors.append)
    return manager


def _wait_until(predicate, timeout=60.0):
    end = time.monotonic() + timeout
    while not predicate():
        if time.monotonic() > end:
            raise AssertionError("not in time")
        QApplication.processEvents()
        time.sleep(0.01)


class TestWhatIsOffered:
    def test_a_file_with_a_finished_loop(self, stored, monkeypatch, tmp_path):
        manager = _manager(_block(tmp_path / "f.mp4", [(1, 2)]), monkeypatch, tmp_path)

        assert manager.is_active_loops_exportable()

    def test_not_one_with_a_loop_begun_alone(self, stored, monkeypatch, tmp_path):
        manager = _manager(
            _block(tmp_path / "f.mp4", [(1, None)]), monkeypatch, tmp_path
        )

        assert not manager.is_active_loops_exportable()

    def test_not_a_stream(self, stored, monkeypatch, tmp_path):
        manager = _manager(_block("https://x/live", [(1, 2)]), monkeypatch, tmp_path)

        assert not manager.is_active_loops_exportable()


class TestWithoutFfmpeg:
    @pytest.fixture(autouse=True)
    def _none(self, monkeypatch):
        monkeypatch.setattr(ffmpeg_tool.shutil, "which", lambda _name: None)

    def test_elsewhere_said_to_install_it(self, stored, monkeypatch, tmp_path):
        monkeypatch.setattr(ffmpeg_tool.env, "IS_WINDOWS", False)
        manager = _manager(_block(tmp_path / "f.mp4", [(1, 2)]), monkeypatch, tmp_path)

        manager.cmd_export_loops()

        assert "Install it" in manager.errors[0]

    def test_on_windows_asked_first(self, stored, monkeypatch, tmp_path):
        monkeypatch.setattr(ffmpeg_tool.env, "IS_WINDOWS", True)
        asked = Mock(return_value=QMessageBox.No)
        monkeypatch.setattr(manager_module.QCustomMessageBox, "question", asked)
        fetched = Mock()
        monkeypatch.setattr(LoopExportManager, "_fetch", fetched)
        manager = _manager(_block(tmp_path / "f.mp4", [(1, 2)]), monkeypatch, tmp_path)

        manager.cmd_export_loops()

        asked.assert_called_once()
        fetched.assert_not_called()

        asked.return_value = QMessageBox.Yes
        manager.cmd_export_loops()

        fetched.assert_called_once()


@needs_ffmpeg
class TestExporting:
    @pytest.fixture
    def film(self, tmp_path):
        source = tmp_path / "film.mp4"
        shutil.copyfile(_media("b.mp4"), source)
        return source

    @pytest.fixture
    def answered(self, monkeypatch, tmp_path):
        """The window answered: these options."""

        options = ExportOptions(
            target=tmp_path / "out.mp4",
            fade_s=0.5,
            order=LoopOrder.TIMELINE,
            quality=ExportQuality.SMALL,
        )
        monkeypatch.setattr(
            manager_module.ExportLoopsDialog, "ask", Mock(return_value=options)
        )
        return options

    @pytest.fixture
    def told(self, monkeypatch):
        told = Mock()
        monkeypatch.setattr(manager_module.QCustomMessageBox, "information", told)
        return told

    def test_made_and_said_where(
        self, stored, monkeypatch, tmp_path, film, answered, told
    ):
        manager = _manager(
            _block(film, [(9000, 12000), (2000, 5000)]), monkeypatch, tmp_path
        )

        manager.cmd_export_loops()
        _wait_until(lambda: not manager.is_busy)

        assert manager.errors == []
        length, streams = _probe(answered.target)
        assert length == pytest.approx(5.5, abs=0.1)
        assert streams == ["video", "audio"]
        assert told.call_args.kwargs["info"] == str(answered.target)
        # asked as it was answered, the next time
        assert stored.get("export/loop_quality") == ExportQuality.SMALL

    def test_cancelled_nothing_left(
        self, stored, monkeypatch, tmp_path, film, answered, told
    ):
        manager = _manager(_block(film, [(1000, 19000)]), monkeypatch, tmp_path)

        manager.cmd_export_loops()
        manager._cancel()
        _wait_until(lambda: not manager.is_busy)

        assert not answered.target.exists()
        told.assert_not_called()
        assert manager.errors == []

    def test_failed_said_with_what_ffmpeg_said(
        self, stored, monkeypatch, tmp_path, answered, told
    ):
        broken = tmp_path / "broken.mp4"
        broken.write_bytes(b"not a video")
        manager = _manager(_block(broken, [(0, 1000)]), monkeypatch, tmp_path)

        manager.cmd_export_loops()
        _wait_until(lambda: not manager.is_busy)

        assert manager.errors[0].startswith("Couldn't export the loops.")
        assert not answered.target.exists()

    def test_never_over_the_video_itself(self, stored, monkeypatch, tmp_path, film):
        options = ExportOptions(film, 0.5, LoopOrder.TIMELINE, ExportQuality.HIGH)
        monkeypatch.setattr(
            manager_module.ExportLoopsDialog, "ask", Mock(return_value=options)
        )
        manager = _manager(_block(film, [(0, 1000)]), monkeypatch, tmp_path)

        manager.cmd_export_loops()

        assert manager.errors == ["Can't export over the video itself."]
        assert film.stat().st_size > 1000
