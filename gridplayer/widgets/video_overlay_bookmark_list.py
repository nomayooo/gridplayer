"""The bookmarks of a cell as a short list over its picture, to pick one to
go to: up in a corner under the title, up and gone with the rest of the
overlay, and only while there are bookmarks.

Kept out of the way: the title's lighter box, smaller than the rest, a few
rows high at most, the rest of them a turn of the wheel away, no wider than
a share of the cell, and not there at all in a cell too small to spare the
room. The one the video is at, or last passed, is picked out.
"""

from PyQt5.QtCore import QPointF, QRectF, QSize, Qt, pyqtSignal
from PyQt5.QtGui import QColor, QFont, QFontMetrics, QPainter, QPolygonF

from gridplayer.models.seek_mark import SeekMarkKind
from gridplayer.utils.time_txt import get_time_txt
from gridplayer.widgets.video_overlay_elements import (
    BOOKMARK_COLOR,
    TITLE_FILL_ALPHA,
    OverlayWidget,
)

# at most this many rows shown at once, the rest a turn of the wheel away
MAX_ROWS = 5
# no wider than this share of the cell
MAX_WIDTH_SHARE = 0.4
# none in a cell smaller than this, which has no room to spare
MIN_CELL_WIDTH = 280
MIN_CELL_HEIGHT = 180

# its text this much smaller than the rest of the overlay's
FONT_SCALE = 0.9
ROW_PADDING = 3
# above and below the rows, where there are more to scroll to: the room for
# an arrow saying so, and how big that is
ARROW_SPACE = 8
ARROW_SIZE = 4
# a name never squeezed narrower than this, for a short one to be read
MIN_NAME_WIDTH = 24
SIDE_PADDING = 6
DOT_SIZE = 6
GAP = 6
# the time, quieter than the name
TIME_ALPHA = 0.7


class OverlayBookmarkList(OverlayWidget):
    # a bookmark picked, by its time, as a marker clicked on says it
    bookmark_clicked = pyqtSignal(tuple)

    fill_alpha = TITLE_FILL_ALPHA

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        # each bookmark as (time, name, colour), first to last
        self._rows: list[tuple[int, str, str]] = []
        self._length = 0
        self._now_ms = 0

        # the first row shown, scrolled down to
        self._first = 0
        self._hovered: int | None = None

        font = QFont(self.font())
        font.setPointSizeF(font.pointSizeF() * FONT_SCALE)
        self.setFont(font)

        self.setMouseTracking(True)
        self.setCursor(Qt.PointingHandCursor)

        self.setMinimumHeight(0)
        self.hide()

    # what it shows

    @property
    def rows(self) -> list[tuple[int, str, str]]:
        return list(self._rows)

    @property
    def has_rows(self) -> bool:
        return bool(self._rows)

    def set_marks(self, marks):
        """The bar's marks: those that are bookmarks."""

        rows = sorted(
            (mark.time_ms, mark.label, mark.color or BOOKMARK_COLOR)
            for mark in marks
            if mark.kind == SeekMarkKind.BOOKMARK
        )

        if rows == self._rows:
            return

        self._rows = rows
        self._first = min(self._first, self._last_first())
        self._hovered = None

        self.updateGeometry()
        self.update()

    def set_time(self, now_ms: int, length: int):
        current = self.current_row
        is_new_length = length != self._length

        self._now_ms = now_ms
        self._length = length

        # its times written for the length, 1:05 or 0:01:05, as wide as that
        if is_new_length:
            self.updateGeometry()
            self.update()
        elif self.current_row != current:
            self.update()

    @property
    def current_row(self) -> int | None:
        """The one the video is at, or last passed."""

        passed = [
            i for i, (time_ms, *_) in enumerate(self._rows) if time_ms <= self._now_ms
        ]

        return passed[-1] if passed else None

    @property
    def shown_rows(self) -> range:
        return range(self._first, min(self._first + MAX_ROWS, len(self._rows)))

    # its size

    def _row_height(self) -> int:
        return QFontMetrics(self.font()).height() + ROW_PADDING * 2

    def _time_txt(self, time_ms: int) -> str:
        length_s = self._length // 1000 if self._length else None
        return get_time_txt(time_ms // 1000, length_s, strip=True)

    def _bold_font(self) -> QFont:
        font = QFont(self.font())
        font.setBold(True)
        return font

    def _is_scrollable(self) -> bool:
        return len(self._rows) > MAX_ROWS

    def _rows_top(self) -> int:
        return ROW_PADDING + (ARROW_SPACE if self._is_scrollable() else 0)

    def sizeHint(self) -> QSize:
        # as wide as any is in bold, as the one picked out is
        metrics = QFontMetrics(self._bold_font())

        names = max(
            (metrics.horizontalAdvance(name) for _, name, _ in self._rows), default=0
        )
        times = max(
            (metrics.horizontalAdvance(self._time_txt(t)) for t, *_ in self._rows),
            default=0,
        )

        width = (
            SIDE_PADDING * 2
            + DOT_SIZE
            + GAP
            + max(names, MIN_NAME_WIDTH)
            + GAP * 2
            + times
        )
        height = self._row_height() * len(self.shown_rows) + self._rows_top() * 2

        return QSize(width, height)

    def minimumSizeHint(self) -> QSize:
        return QSize(0, self.sizeHint().height())

    # drawn

    def paintEvent(self, event):
        if not self._rows:
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        self.paint_box(painter)

        row_height = self._row_height()
        current = self.current_row

        for place, index in enumerate(self.shown_rows):
            time_ms, name, color = self._rows[index]
            top = self._rows_top() + place * row_height
            row = QRectF(0, top, self.width(), row_height)

            text_color = self.text_color

            if index == self._hovered:
                painter.fillRect(row, self.hover_fill_color)
                text_color = self.hover_text_color

            # its own colour, as its marker on the bar
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor(color))
            painter.drawEllipse(
                QRectF(
                    SIDE_PADDING,
                    top + (row_height - DOT_SIZE) / 2,
                    DOT_SIZE,
                    DOT_SIZE,
                )
            )

            font = QFont(self.font())
            font.setBold(index == current)
            painter.setFont(font)
            bold_metrics = QFontMetrics(font)

            time_txt = self._time_txt(time_ms)
            time_width = bold_metrics.horizontalAdvance(time_txt)

            text_left = SIDE_PADDING + DOT_SIZE + GAP
            name_width = self.width() - text_left - GAP * 2 - time_width - SIDE_PADDING
            name_txt = bold_metrics.elidedText(name, Qt.ElideRight, max(name_width, 0))

            painter.setPen(text_color)
            painter.drawText(
                QRectF(text_left, top, max(name_width, 0), row_height),
                Qt.AlignVCenter | Qt.AlignLeft,
                name_txt,
            )

            quiet = QColor(text_color)
            quiet.setAlphaF(TIME_ALPHA)
            painter.setPen(quiet)
            painter.drawText(
                QRectF(0, top, self.width() - SIDE_PADDING, row_height),
                Qt.AlignVCenter | Qt.AlignRight,
                time_txt,
            )

        self._paint_more(painter)

    def _paint_more(self, painter):
        """A small arrow above or below the rows, in a room of its own,
        where there are more that way."""

        quiet = QColor(self.text_color)
        quiet.setAlphaF(TIME_ALPHA)
        painter.setPen(Qt.NoPen)
        painter.setBrush(quiet)

        middle = self.width() / 2
        half = ARROW_SIZE

        if self._first > 0:
            tip = ROW_PADDING + (ARROW_SPACE - ARROW_SIZE) / 2
            painter.drawPolygon(
                QPolygonF(
                    [
                        QPointF(middle, tip),
                        QPointF(middle - half, tip + ARROW_SIZE),
                        QPointF(middle + half, tip + ARROW_SIZE),
                    ]
                )
            )

        if self._first < self._last_first():
            tip = self.height() - ROW_PADDING - (ARROW_SPACE - ARROW_SIZE) / 2
            painter.drawPolygon(
                QPolygonF(
                    [
                        QPointF(middle, tip),
                        QPointF(middle - half, tip - ARROW_SIZE),
                        QPointF(middle + half, tip - ARROW_SIZE),
                    ]
                )
            )

    # picked

    def row_at(self, y: int) -> int | None:
        top = self._rows_top()
        place = int((y - top) // self._row_height())

        if y < top or place >= len(self.shown_rows):
            return None

        return self.shown_rows[place]

    def mouseMoveEvent(self, event):
        hovered = self.row_at(event.pos().y())

        if hovered != self._hovered:
            self._hovered = hovered
            self.update()

        event.accept()

    def leaveEvent(self, event):
        if self._hovered is not None:
            self._hovered = None
            self.update()

        super().leaveEvent(event)

    def mousePressEvent(self, event):
        # taken here, not by the cell behind, which a click pauses
        event.accept()

    def mouseReleaseEvent(self, event):
        event.accept()

        if event.button() != Qt.LeftButton:
            return

        index = self.row_at(event.pos().y())

        if index is not None:
            self.bookmark_clicked.emit((self._rows[index][0],))

    def mouseDoubleClickEvent(self, event):
        # not the cell's, which a double click makes the only one shown
        event.accept()

    def wheelEvent(self, event):
        """Through them, where there are more than it shows; the cell's to
        seek with otherwise."""

        if len(self._rows) <= MAX_ROWS:
            event.ignore()
            return

        step = -1 if event.angleDelta().y() > 0 else 1
        first = max(0, min(self._first + step, self._last_first()))

        if first != self._first:
            self._first = first
            self._hovered = self.row_at(event.pos().y())
            self.update()

        event.accept()

    def _last_first(self) -> int:
        return max(0, len(self._rows) - MAX_ROWS)

    # where it fits

    @staticmethod
    def has_room(width: int, height: int) -> bool:
        return width >= MIN_CELL_WIDTH and height >= MIN_CELL_HEIGHT

    @staticmethod
    def max_width_in(width: int) -> int:
        return int(width * MAX_WIDTH_SHARE)
