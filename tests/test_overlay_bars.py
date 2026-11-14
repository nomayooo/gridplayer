"""The seek and the volume bars over a video: how their parts are painted."""

import pytest
from PyQt5.QtCore import QPoint, Qt
from PyQt5.QtGui import QColor, QImage, QPainter

from gridplayer.widgets.video_overlay_elements import (
    BAR_PROGRESS_COLOR,
    BAR_PROGRESS_COLOR_ON_RED,
    BAR_SELECT_COLOR,
    BOX_FILL_ALPHA,
    BOX_RADIUS,
    LOOP_COLORS,
    LOOP_MARK_EDGE_COLOR,
    LOOP_MARK_TAB_LENGTH,
    LOOP_MARK_WIDTH,
    OTHER_LOOP_MARK_WIDTH,
    OverlayLabel,
    OverlayProgressBar,
    OverlayVolumeBar,
    loop_color,
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


WAITING_COLOR = LOOP_COLORS[1]


class TestLoopMarks:
    """On the 200px bar: the loop playing from 50px to 100px, another
    waiting from 150px to 180px."""

    @pytest.fixture
    def image(self, seek_bar):
        seek_bar.loop_start = 0.25
        seek_bar.loop_end = 0.5
        seek_bar.loop_color = loop_color(0)
        seek_bar.other_loops = ((0.75, 0.9, WAITING_COLOR),)

        return _over_dark_picture(seek_bar)

    @pytest.mark.parametrize("x", [50, 100])
    def test_the_loop_playing_in_its_colour_and_widest(self, image, x):
        assert _line_at(image, x, image.height() // 2) == (
            loop_color(0),
            LOOP_MARK_WIDTH,
        )

    @pytest.mark.parametrize("x", [150, 180])
    def test_one_waiting_in_its_own_colour_both_ends(self, image, x):
        assert _line_at(image, x, image.height() // 2) == (
            WAITING_COLOR,
            OTHER_LOOP_MARK_WIDTH,
        )

    @pytest.mark.parametrize(("x", "width"), [(50, 3), (150, 2)])
    def test_each_line_edged_in_black(self, image, x, width):
        middle = image.height() // 2
        left = x - width // 2 - 1
        right = left + width + 1

        for edge in (left, right):
            assert QColor(image.pixel(edge, middle)).name() == LOOP_MARK_EDGE_COLOR

    def test_a_start_reaches_in_to_the_right_an_end_to_the_left(self, image):
        """As "[" and "]": the top of each, a pixel down."""

        start_tab = 50 - LOOP_MARK_WIDTH // 2 + LOOP_MARK_WIDTH + 1
        end_tab = 100 - LOOP_MARK_WIDTH // 2 - 2

        assert QColor(image.pixel(start_tab, 1)).name() == loop_color(0)
        assert QColor(image.pixel(end_tab, 1)).name() == loop_color(0)
        # and not out the other way
        outside_start = 50 - LOOP_MARK_WIDTH // 2 - 3
        assert QColor(image.pixel(outside_start, 1)).name() != loop_color(0)

    def test_the_lines_are_3_and_2_pixels(self):
        assert (LOOP_MARK_WIDTH, OTHER_LOOP_MARK_WIDTH) == (3, 2)
        assert LOOP_MARK_TAB_LENGTH >= 3


def _contrast(a, b):
    def luminance(color):
        def channel(c):
            c /= 255
            return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4

        q = QColor(color)
        return (
            0.2126 * channel(q.red())
            + 0.7152 * channel(q.green())
            + 0.0722 * channel(q.blue())
        )

    high, low = sorted((luminance(a), luminance(b)), reverse=True)
    return (high + 0.05) / (low + 0.05)


class TestLoopColours:
    """Told apart from one another, and seen on any bar: the black edge
    against the bar at least 3:1, as WCAG asks of a graphic, and each colour
    against its edge."""

    BARS = (
        BAR_PROGRESS_COLOR,
        BAR_PROGRESS_COLOR_ON_RED,
        BAR_SELECT_COLOR,
        "#f2f2f2",
        "#ffffff",
    )

    @pytest.mark.parametrize("bar", BARS)
    def test_the_edge_stands_out_on_every_bar(self, bar):
        assert _contrast(LOOP_MARK_EDGE_COLOR, bar) >= 3

    @pytest.mark.parametrize("color", LOOP_COLORS)
    def test_each_colour_stands_out_on_its_edge(self, color):
        assert _contrast(color, LOOP_MARK_EDGE_COLOR) >= 4.5

    def test_none_red_pink_or_the_bookmarks_amber(self):
        for color in LOOP_COLORS:
            hue = QColor(color).hue()
            # white has none
            # red and pink round 0, the bookmarks amber at 40
            assert hue == -1 or 50 <= hue <= 290, color

    def test_all_apart(self):
        assert len(set(LOOP_COLORS)) == len(LOOP_COLORS) >= 5

    def test_round_again_past_the_last(self):
        assert loop_color(len(LOOP_COLORS)) == loop_color(0)


class TestSeeThrough:
    def test_the_title_lets_half_the_picture_through(self):
        title = OverlayLabel()

        assert title.fill_color.alphaF() == pytest.approx(0.5, abs=0.01)

        title.close()

    def test_the_other_boxes_keep_theirs(self, seek_bar):
        assert BOX_FILL_ALPHA == 0.7
        assert seek_bar.fill_color.alphaF() == pytest.approx(0.7, abs=0.01)
