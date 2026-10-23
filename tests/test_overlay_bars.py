"""The seek and the volume bars over a video: how their parts are painted."""

import pytest
from PyQt5.QtCore import QPoint, Qt
from PyQt5.QtGui import QColor, QImage, QPainter

from gridplayer.widgets.video_overlay_elements import (
    BOX_FILL_ALPHA,
    BOX_RADIUS,
    LOOP_MARK_COLOR,
    LOOP_MARK_WIDTH,
    OTHER_LOOP_MARK_COLOR,
    OTHER_LOOP_MARK_WIDTH,
    OverlayLabel,
    OverlayProgressBar,
    OverlayVolumeBar,
)

DARK_PICTURE = QColor("#101010")


def _over_dark_picture(bar):
    image = QImage(bar.size(), QImage.Format_RGB32)
    image.fill(DARK_PICTURE)

    painter = QPainter(image)
    bar.render(painter, QPoint(0, 0))
    painter.end()

    return image


def _corner_pixels(image, corners):
    reach = int(BOX_RADIUS) + 1

    for corner_x, corner_y in corners:
        for dx in range(reach):
            for dy in range(reach):
                x = corner_x + dx if corner_x == 0 else corner_x - dx
                y = corner_y + dy if corner_y == 0 else corner_y - dy

                yield QColor(image.pixel(x, y))


def _assert_only_progress_and_picture(pixels, progress):
    """Each pixel the progress over the picture, partly or wholly, with none
    of the box's own fill showing round it."""

    for pixel in pixels:
        share = (pixel.red() - DARK_PICTURE.red()) / (
            progress.red() - DARK_PICTURE.red()
        )

        green = DARK_PICTURE.green() + share * (progress.green() - DARK_PICTURE.green())

        assert pixel.green() == pytest.approx(green, abs=3), pixel.name()


@pytest.fixture
def seek_bar():
    bar = OverlayProgressBar()
    bar.setAttribute(Qt.WA_DontShowOnScreen)
    bar.resize(200, 23)
    bar.color = QColor(Qt.white)

    yield bar

    bar.close()


@pytest.fixture
def volume_bar():
    bar = OverlayVolumeBar()
    bar.setAttribute(Qt.WA_DontShowOnScreen)
    bar.resize(23, 100)
    bar.color = QColor(Qt.white)

    yield bar

    bar.close()


class TestRoundedCorners:
    def test_the_seek_bar_has_no_pale_fringe_round_the_progress(self, seek_bar):
        seek_bar.position = 0.5

        image = _over_dark_picture(seek_bar)
        bottom = image.height() - 1

        _assert_only_progress_and_picture(
            _corner_pixels(image, [(0, 0), (0, bottom)]), seek_bar.color_progress
        )

    def test_the_volume_bar_has_no_pale_fringe_round_the_volume(self, volume_bar):
        volume_bar.position = 0.5

        image = _over_dark_picture(volume_bar)
        right = image.width() - 1
        bottom = image.height() - 1

        _assert_only_progress_and_picture(
            _corner_pixels(image, [(0, bottom), (right, bottom)]),
            volume_bar.color_progress,
        )


class TestAheadOfTheMouse:
    def test_it_stands_apart_from_the_bar_over_a_dark_picture(self, seek_bar):
        seek_bar.position = 0.2
        seek_bar.progress_select_x = 150
        seek_bar.underMouse = lambda: True

        image = _over_dark_picture(seek_bar)
        middle = image.height() // 2

        ahead = QColor(image.pixel(100, middle))
        rest = QColor(image.pixel(180, middle))

        assert ahead.name() == seek_bar.color_ahead.name()
        assert ahead.blue() - ahead.red() > 60
        assert abs(rest.blue() - rest.red()) < 5


def _line_at(image, x, y):
    """The colour at x, and how many pixels wide it runs there."""

    color = image.pixel(x, y)

    left = x
    while left > 0 and image.pixel(left - 1, y) == color:
        left -= 1

    right = x
    while right < image.width() - 1 and image.pixel(right + 1, y) == color:
        right += 1

    return QColor(color).name(), right - left + 1


class TestLoopMarks:
    """On the 200px bar: the loop playing from 50px to 100px, another
    waiting from 150px to 180px."""

    @pytest.fixture
    def image(self, seek_bar):
        seek_bar.loop_start = 0.25
        seek_bar.loop_end = 0.5
        seek_bar.other_loops = ((0.75, 0.9),)

        return _over_dark_picture(seek_bar)

    @pytest.mark.parametrize("x", [50, 100])
    def test_the_loop_playing_is_green_and_widest(self, image, x):
        assert _line_at(image, x, image.height() // 2) == (
            LOOP_MARK_COLOR,
            LOOP_MARK_WIDTH,
        )

    @pytest.mark.parametrize("x", [150, 180])
    def test_the_loops_waiting_are_blue(self, image, x):
        assert _line_at(image, x, image.height() // 2) == (
            OTHER_LOOP_MARK_COLOR,
            OTHER_LOOP_MARK_WIDTH,
        )

    def test_a_loop_alone_is_green_and_widest_too(self, seek_bar):
        seek_bar.loop_start = 0.25
        seek_bar.loop_end = 0.5

        image = _over_dark_picture(seek_bar)

        assert _line_at(image, 50, image.height() // 2) == (
            LOOP_MARK_COLOR,
            LOOP_MARK_WIDTH,
        )

    def test_the_lines_are_3_and_2_pixels(self):
        assert (LOOP_MARK_WIDTH, OTHER_LOOP_MARK_WIDTH) == (3, 2)


class TestSeeThrough:
    def test_the_title_lets_half_the_picture_through(self):
        title = OverlayLabel()

        assert title.fill_color.alphaF() == pytest.approx(0.5, abs=0.01)

        title.close()

    def test_the_other_boxes_keep_theirs(self, seek_bar):
        assert BOX_FILL_ALPHA == 0.7
        assert seek_bar.fill_color.alphaF() == pytest.approx(0.7, abs=0.01)
