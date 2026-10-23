"""The picture of the time under the mouse on the seek bar: the hover label
it is shown in, the previewer it is asked of, and the cell's part that asks.

The frames themselves are read by VLC in a process of their own, which the
real-app scenario seek_preview drives.
"""

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from PyQt5.QtCore import QPoint, Qt
from PyQt5.QtGui import QColor, QImage

from gridplayer.models.seek_mark import SeekMark, SeekMarkKind
from gridplayer.utils import seek_preview
from gridplayer.utils.seek_preview import SeekPreviewer, preview_size
from gridplayer.widgets.video_block_preview import PreviewControl
from gridplayer.widgets.video_overlay import OverlayBlock
from gridplayer.widgets.video_overlay_elements import (
    HOVER_PREVIEW_GAP_PX,
    HOVER_PREVIEW_PX,
)

LENGTH = 60000
FILE = Path("/videos/a.mp4").absolute()


def _picture(width=320, height=180, color="#3070c0"):
    picture = QImage(width, height, QImage.Format_RGB32)
    picture.fill(QColor(color))
    return picture


@pytest.fixture
def overlay():
    overlay = OverlayBlock()
    overlay.setAttribute(Qt.WA_DontShowOnScreen)
    overlay.resize(520, 300)
    overlay.set_color("#ffffff")
    overlay.set_position(27000, LENGTH)
    overlay.show()

    yield overlay

    overlay.close()


def _hover(overlay, fraction=0.5):
    bar = overlay.progress_bar
    x = round(bar.width() * fraction)

    overlay.floating_progress.on_mouse_over(
        bar.mapToParent(QPoint(x, 0)), x / bar.width(), bar.width()
    )

    return overlay.floating_progress


class TestTheLabel:
    def test_hovering_asks_for_the_picture_at_the_time(self, overlay):
        wanted = []
        overlay.preview_wanted.connect(wanted.append)

        _hover(overlay, 0.5)

        bar_width = overlay.progress_bar.width()
        x = round(bar_width * 0.5)
        assert wanted == [int(LENGTH * (x / bar_width))]

    def test_it_is_shown_above_the_time(self, overlay):
        label = _hover(overlay)
        bare = label.size()

        overlay.set_preview(_picture(320, 180))

        assert label.preview is not None
        assert label.width() >= HOVER_PREVIEW_PX
        assert label.height() == bare.height() + 90 + HOVER_PREVIEW_GAP_PX

    def test_a_tall_picture_is_as_tall_as_a_wide_one_is_wide(self, overlay):
        label = _hover(overlay)
        bare = label.size()

        overlay.set_preview(_picture(180, 320))

        assert label.height() == bare.height() + HOVER_PREVIEW_PX + HOVER_PREVIEW_GAP_PX

    def test_the_label_stays_over_the_mouse_with_it(self, overlay):
        label = _hover(overlay, 0.5)
        overlay.set_preview(_picture())

        bar = overlay.progress_bar
        mouse_y = bar.mapToParent(QPoint(0, 0)).y()

        assert label.geometry().bottom() + 1 == mouse_y

    def test_it_is_drawn(self, overlay):
        label = _hover(overlay)
        overlay.set_preview(_picture(color="#3070c0"))

        image = label.grab().toImage()
        middle = image.pixelColor(image.width() // 2, 5 + 45)

        assert middle.name() == "#3070c0"

    def test_a_cell_too_short_for_it_shows_the_time_alone(self, overlay):
        overlay.resize(520, 90)
        label = _hover(overlay)
        bare = label.size()

        overlay.set_preview(_picture())

        assert label.size() == bare

    def test_it_goes_with_the_mouse(self, overlay):
        label = _hover(overlay)
        overlay.set_preview(_picture())

        overlay.progress_bar.mouse_left.emit()

        assert label.preview is None
        assert not label.isVisible()

    def test_none_over_a_bookmarks_marker(self, overlay):
        label = _hover(overlay)
        overlay.set_preview(_picture())
        with_picture = label.height()

        label.on_marker_over(
            QPoint(200, 250), (SeekMark(27000, "Here", SeekMarkKind.BOOKMARK),), 400
        )

        assert label.height() < with_picture


class TestThePreviewer:
    @pytest.fixture
    def previewer(self, monkeypatch):
        previewer = SeekPreviewer()

        # no process: what is asked of it is noted
        sent = []
        conn = SimpleNamespace(send=sent.append)
        monkeypatch.setattr(previewer, "_connection", lambda: conn)
        previewer.sent = sent

        yield previewer

        previewer.close()

    def test_a_picture_not_had_is_asked_of_the_process(self, previewer):
        previewer.request(FILE, 5000, Mock())

        assert previewer.sent == [(str(FILE), 5000)]

    def test_a_picture_read_goes_to_the_one_who_asked_last(self, previewer):
        first, last = Mock(), Mock()
        picture = _picture()

        previewer.request(FILE, 5000, first)
        previewer.request(FILE, 6000, last)
        previewer._on_frame_read(FILE, 6000, picture)

        first.assert_not_called()
        last.assert_called_once_with(FILE, 6000, picture)

    def test_one_read_before_is_given_at_once(self, previewer):
        picture = _picture()
        previewer._on_frame_read(FILE, 5000, picture)
        previewer.sent.clear()

        receiver = Mock()
        previewer.request(FILE, 5000, receiver)

        receiver.assert_called_once_with(FILE, 5000, picture)
        assert previewer.sent == []

    def test_only_so_many_are_kept(self, previewer):
        for time_ms in range(seek_preview.FRAMES_KEPT + 5):
            previewer._on_frame_read(FILE, time_ms, _picture())

        assert len(previewer._frames) == seek_preview.FRAMES_KEPT
        assert (FILE, 0) not in previewer._frames

    def test_a_file_that_could_not_be_read_is_not_asked_about_again(self, previewer):
        previewer._unreadable.add(FILE)

        previewer.request(FILE, 5000, Mock())

        assert previewer.sent == []
        assert not previewer.is_readable(FILE)

    def test_a_file_the_process_went_down_on_is_not_asked_about_again(self, previewer):
        previewer.request(FILE, 5000, Mock())

        conn = object()
        previewer._conn = conn
        previewer._process_gone(conn)

        assert not previewer.is_readable(FILE)


class TestTheSize:
    @pytest.mark.parametrize(
        ("size", "read"),
        [
            ((1920, 1080), (320, 180)),
            ((1080, 1920), (180, 320)),
            # never made bigger
            ((160, 90), (160, 90)),
            ((0, 0), (0, 0)),
        ],
    )
    def test_frames_are_read_as_they_are_shaped(self, size, read):
        assert preview_size(*size) == read


class TestTheCell:
    @pytest.fixture
    def block(self, monkeypatch):
        settings = {"player/seek_preview": True}
        monkeypatch.setattr(
            "gridplayer.widgets.video_block_preview.Settings",
            lambda: SimpleNamespace(get=settings.get),
        )

        previewer = Mock()
        previewer.is_readable.return_value = True

        block = SimpleNamespace(
            is_video_initialized=True,
            is_live=False,
            is_local_file=True,
            video_tracks=[1],
            video_params=SimpleNamespace(uri=FILE),
            overlay=Mock(),
            _ctx=SimpleNamespace(seek_preview=previewer),
        )
        block.settings = settings

        return block

    def _asked(self, block):
        return block._ctx.seek_preview.request.call_args_list

    def test_it_asks_for_the_file_at_the_time(self, block):
        PreviewControl(block).want(5000)

        ((path, time_ms, _),) = [c.args for c in self._asked(block)]
        assert (path, time_ms) == (FILE, 5000)

    @pytest.mark.parametrize(
        "change",
        [
            {"is_local_file": False},
            {"is_live": True},
            {"video_tracks": []},
            {"is_video_initialized": False},
        ],
    )
    def test_not_for_what_is_not_a_video_file(self, block, change):
        for name, value in change.items():
            setattr(block, name, value)

        PreviewControl(block).want(5000)

        assert self._asked(block) == []

    def test_not_with_the_setting_off(self, block):
        block.settings["player/seek_preview"] = False

        PreviewControl(block).want(5000)

        assert self._asked(block) == []

    def test_the_picture_goes_to_the_overlay(self, block, monkeypatch):
        monkeypatch.setattr(
            "gridplayer.widgets.video_block_preview.sip.isdeleted", lambda _: False
        )
        picture = _picture()

        part = PreviewControl(block)
        part.want(5000)
        receiver = self._asked(block)[0].args[2]
        receiver(FILE, 5000, picture)

        block.overlay.set_preview.assert_called_once_with(picture)

    def test_not_if_the_cell_plays_another_file_by_then(self, block, monkeypatch):
        monkeypatch.setattr(
            "gridplayer.widgets.video_block_preview.sip.isdeleted", lambda _: False
        )

        part = PreviewControl(block)
        part.want(5000)
        receiver = self._asked(block)[0].args[2]

        block.video_params.uri = Path("/videos/b.mp4").absolute()
        receiver(FILE, 5000, _picture())

        block.overlay.set_preview.assert_not_called()
