"""The list of folders to pick from, in Add, Add All, Import and Move To:
each folder drawn in by how deep it is, its icon with its name, rather than
its name pushed along by spaces."""

from PyQt5.QtCore import QRect, QSize
from PyQt5.QtGui import QColor, QIcon, QImage, QPainter, QPixmap
from PyQt5.QtWidgets import QStyle, QStyleOptionViewItem

from gridplayer.dialogs import favourites as dialogs
from gridplayer.dialogs.favourites import (
    FOLDER_INDENT,
    ITEM_DEPTH,
    AddAllFavouritesDialog,
    AddFavouriteDialog,
    ImportPlaylistsDialog,
)
from tests.test_favourites import (
    _favourites,
    undated,  # noqa: F401 (autouse here too)
)

ICON = QColor("orange")


def _rows(box):
    return [(box.itemData(i, ITEM_DEPTH), box.itemText(i)) for i in range(box.count())]


SHOWN = [(0, "Favourites"), (1, "Music"), (2, "Live"), (1, "Empty")]


def test_each_window_lists_them_by_depth_names_as_they_are():
    for dialog in (
        AddAllFavouritesDialog(_favourites(), count=1, left_out=0),
        AddFavouriteDialog(_favourites(), name="Clip", loops=0),
        ImportPlaylistsDialog(_favourites(), names=["List"]),
    ):
        assert _rows(dialog.folder) == SHOWN


def _icon_left(monkeypatch, row: int) -> int:
    """Where the icon of a row of the list is drawn from the left."""

    pixmap = QPixmap(16, 16)
    pixmap.fill(ICON)
    monkeypatch.setattr(dialogs.QIcon, "fromTheme", lambda *_a: QIcon(pixmap))

    dialog = AddAllFavouritesDialog(_favourites(), count=1, left_out=0)
    box = dialog.folder
    delegate = box.itemDelegate()
    index = box.model().index(row, 0)

    option = QStyleOptionViewItem()
    option.rect = QRect(0, 0, 300, 24)
    option.state = QStyle.State_Enabled
    option.decorationSize = QSize(16, 16)
    option.palette = box.palette()
    option.font = box.font()
    option.fontMetrics = box.fontMetrics()

    image = QImage(300, 24, QImage.Format_ARGB32)
    image.fill(QColor("white"))
    painter = QPainter(image)
    delegate.paint(painter, option, index)
    painter.end()

    return next(x for x in range(300) if image.pixelColor(x, 12).rgb() == ICON.rgb())


def test_the_icon_drawn_in_with_its_name(monkeypatch):
    top = _icon_left(monkeypatch, 0)

    assert _icon_left(monkeypatch, 1) == top + FOLDER_INDENT
    assert _icon_left(monkeypatch, 2) == top + 2 * FOLDER_INDENT


def test_room_made_for_how_far_in():
    dialog = AddAllFavouritesDialog(_favourites(), count=1, left_out=0)
    box = dialog.folder
    delegate = box.itemDelegate()
    option = QStyleOptionViewItem()
    option.font = box.font()
    option.fontMetrics = box.fontMetrics()

    # "Live", two deep
    live = delegate.sizeHint(option, box.model().index(2, 0)).width()
    flat = dialogs.QStyledItemDelegate().sizeHint(option, box.model().index(2, 0))

    assert live == flat.width() + 2 * FOLDER_INDENT
