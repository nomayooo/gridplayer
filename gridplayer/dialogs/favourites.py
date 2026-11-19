"""The favourites' windows, as a web browser has them: one to make the active
video a favourite, in a folder of the viewer's picking, and one to put them
in order, in folders made, renamed, moved about and removed."""

from pathlib import Path

from PyQt5.QtCore import (
    QDateTime,
    QEvent,
    QItemSelectionModel,
    QLocale,
    QPoint,
    Qt,
    QTimer,
    pyqtSignal,
)
from PyQt5.QtGui import QColor, QCursor, QIcon, QKeySequence, QPixmap
from PyQt5.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QShortcut,
    QStyle,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
)

from gridplayer.dialogs.input_dialog import QCustomTextInput
from gridplayer.dialogs.messagebox import QCustomMessageBox
from gridplayer.models.favourites import (
    FavouriteFolder,
    Favourites,
    FavouriteVideo,
    FolderPath,
    added_now,
    folders_within,
    newest,
    sorted_by,
    videos_in,
)
from gridplayer.params.static import FavouritesSort
from gridplayer.settings import Settings
from gridplayer.utils.qt import count_txt, translate
from gridplayer.utils.time_txt import ms_time_txt

# how far in a folder is drawn in a list of them, its icon and name both,
# for each folder it is within, in pixels
FOLDER_INDENT = 20
# where a folder of such a list keeps how deep it is
ITEM_DEPTH = Qt.UserRole + 10

# what an item of the tree is: a video's favourite, or nothing for a folder
ITEM_FAVOURITE = Qt.UserRole
# when a folder was added, None for one added before favourites kept it
ITEM_ADDED = Qt.UserRole + 1
# where it is in the folder's own order, while they are shown sorted
ITEM_ORDER = Qt.UserRole + 2

COLUMN_ADDED = 4


def _loop_start_txt(loop_start: int) -> str:
    return translate("Favourites", "start at {TIME}").format(
        TIME=ms_time_txt(loop_start, strip=True)
    )


def _added_txt(added) -> str:
    if added is None:
        return ""

    return QLocale().toString(
        QDateTime.fromSecsSinceEpoch(int(added.timestamp())), QLocale.ShortFormat
    )


def _added_of(tree_item):
    """As the tree has it now: for a folder, the latest of it and all it
    holds (models.favourites.latest_added)."""

    video = tree_item.data(0, ITEM_FAVOURITE)

    if video is not None:
        return video.added

    return newest(
        [
            tree_item.data(0, ITEM_ADDED),
            *(_added_of(tree_item.child(i)) for i in range(tree_item.childCount())),
        ]
    )


def _all_within(parent_item) -> list:
    found = []

    for index in range(parent_item.childCount()):
        child = parent_item.child(index)
        found.append(child)
        found.extend(_all_within(child))

    return found


class _IndentedFolders(QStyledItemDelegate):
    """A list of folders, each drawn in from the left, its icon and its name
    together, by how deep it is: the folders within one under it, as in a
    tree. The row picked highlighted all the way across."""

    def paint(self, painter, option, index):
        depth = index.data(ITEM_DEPTH) or 0

        if option.state & QStyle.State_Selected:
            painter.fillRect(option.rect, option.palette.highlight())

        shifted = QStyleOptionViewItem(option)
        shifted.rect = option.rect.adjusted(FOLDER_INDENT * depth, 0, 0, 0)
        # no frame of its own around the part drawn in
        shifted.state &= ~QStyle.State_HasFocus

        super().paint(painter, shifted, index)

    def sizeHint(self, option, index):
        size = super().sizeHint(option, index)
        size.setWidth(size.width() + FOLDER_INDENT * (index.data(ITEM_DEPTH) or 0))
        return size


def _folder_box(parent) -> QComboBox:
    """A box to pick a folder from, its list showing them as a tree."""

    box = QComboBox(parent)
    box.setMinimumWidth(320)
    box.setItemDelegate(_IndentedFolders(box))

    return box


def _add_folder(box: QComboBox, depth: int, title: str, data) -> None:
    box.addItem(QIcon.fromTheme("favourites-folder"), title, data)
    box.setItemData(box.count() - 1, depth, ITEM_DEPTH)


def _new_folder_name(parent) -> str | None:
    name = QCustomTextInput.get_text(
        parent,
        translate("Favourites", "New Folder"),
        placeholder=translate("Favourites", "Folder name"),
    )

    name = (name or "").strip()

    return name or None


class _InFolderDialog(QDialog):
    """Favourites made in a folder of the viewer's picking, or of their
    making, to be put in on OK: the folder picked, and the buttons."""

    def __init__(self, favourites: Favourites, **kwargs):
        super().__init__(**kwargs)

        # a copy, which folders made here go into, kept only on OK
        self.favourites = favourites.model_copy(deep=True)

        self.folder = _folder_box(self)

        self.new_folder_button = QPushButton(
            translate("Favourites", "New Folder..."), self
        )
        self.new_folder_button.clicked.connect(self.new_folder)

        self.buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel, Qt.Horizontal, self
        )
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        self.ok_button = self.buttons.button(QDialogButtonBox.Ok)

    def _folder_row(self) -> QHBoxLayout:
        folder_row = QHBoxLayout()
        folder_row.addWidget(self.folder, 1)
        folder_row.addWidget(self.new_folder_button)
        return folder_row

    def fill_folders(self, selected: FolderPath = ()):
        self.folder.clear()

        for path, names in self.favourites.folders():
            title = names[-1] if names else translate("Favourites", "Favourites")
            _add_folder(self.folder, len(path), title, path)

        # not findData, which goes by the tuple itself rather than its value
        folders = [self.folder.itemData(i) for i in range(self.folder.count())]
        self.folder.setCurrentIndex(
            folders.index(selected) if selected in folders else 0
        )

    @property
    def selected_folder(self) -> FolderPath:
        return self.folder.currentData() or ()

    def new_folder(self):
        name = _new_folder_name(self)

        if name is None:
            return

        parent = self.selected_folder
        self.favourites.add(parent, FavouriteFolder(name=name, added=added_now()))

        new_path = (*parent, len(self.favourites.items_at(parent)) - 1)
        self.fill_folders(selected=new_path)


class ImportPlaylistsDialog(_InFolderDialog):
    """Playlists imported, each as a folder of its videos named after it, in
    a folder of the viewer's picking: one under a name the viewer may
    change, several under their own."""

    def __init__(
        self,
        favourites: Favourites,
        names: list[str],
        folder: FolderPath = (),
        **kwargs,
    ):
        super().__init__(favourites, **kwargs)

        self._names = names

        form = QFormLayout()

        if len(names) == 1:
            self.setWindowTitle(translate("Favourites", "Import Playlist"))

            self.name = QLineEdit(names[0], self)
            self.name.setMinimumWidth(320)
            self.name.selectAll()
            self.name.setPlaceholderText(translate("Favourites", "Folder name"))
            self.name.textChanged.connect(
                lambda text: self.ok_button.setEnabled(bool(text.strip()))
            )

            form.addRow(translate("Favourites", "Name:"), self.name)
        else:
            self.setWindowTitle(translate("Favourites", "Import Playlists"))
            self.name = None

        form.addRow(translate("Favourites", "Into:"), self._folder_row())

        layout = QVBoxLayout(self)
        layout.addLayout(form)

        if self.name is None:
            self.count_note = QLabel(
                translate(
                    "Favourites",
                    "Playlists to import: {COUNT}, each into a folder of its name.",
                ).format(COUNT=count_txt(len(names))),
                self,
            )
            self.count_note.setWordWrap(True)
            layout.addWidget(self.count_note)

        layout.addWidget(self.buttons)

        self.fill_folders(selected=folder)

    @property
    def names(self) -> list[str]:
        if self.name is None:
            return list(self._names)

        return [self.name.text().strip()]

    @classmethod
    def ask(
        cls,
        parent,
        favourites: Favourites,
        names: list[str],
        folder: FolderPath = (),
    ):
        """(the favourites with any folders made, the folder picked, the
        names of the folders the playlists go in), None for the viewer
        thinking better of it. The folder given picked to begin with."""

        dialog = cls(favourites=favourites, names=names, folder=folder, parent=parent)

        if not dialog.exec() or not all(dialog.names):
            return None

        return dialog.favourites, dialog.selected_folder, dialog.names


class AddFavouriteDialog(_InFolderDialog):
    """The active video made a favourite: under what name, in which folder."""

    def __init__(
        self,
        favourites: Favourites,
        name: str,
        loops: int,
        loop_start: int | None = None,
        folder: FolderPath = (),
        kept_names: frozenset[str] = frozenset(),
        position: int | None = None,
        **kwargs,
    ):
        super().__init__(favourites, **kwargs)

        self.setWindowTitle(translate("Favourites", "Add to Favourites"))

        self.name = QLineEdit(name, self)
        self.name.setMinimumWidth(320)
        self.name.selectAll()

        self.loops_note = QLabel(self)
        self.loops_note.setVisible(loops > 0)
        self.loops_note.setText(
            translate("Favourites", "A-B loops kept with it: {COUNT}").format(
                COUNT=count_txt(loops)
            )
        )

        # a loop begun and not finished, kept with it too
        self.loop_start_note = QLabel(self)
        self.loop_start_note.setVisible(loop_start is not None)
        if loop_start is not None:
            self.loop_start_note.setText(
                translate("Favourites", "A-B loop start kept with it: {TIME}").format(
                    TIME=ms_time_txt(loop_start, strip=True)
                )
            )

        # where it opens, as it is now
        self.position_note = QLabel(self)
        self.position_note.setVisible(position is not None)
        if position is not None:
            self.position_note.setText(
                translate("Favourites", "Opens at {TIME}").format(
                    TIME=ms_time_txt(position, strip=True)
                )
            )

        # a favourite already under the name, which this one takes the place
        # of; under another name, one more
        self.kept_note = QLabel(
            translate("Favourites", "Already in your favourites: this replaces it."),
            self,
        )
        self._kept_names = kept_names

        self.name.textChanged.connect(self._name_changed)

        form = QFormLayout()
        form.addRow(translate("Favourites", "Name:"), self.name)
        form.addRow(translate("Favourites", "Folder:"), self._folder_row())

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(self.position_note)
        layout.addWidget(self.loops_note)
        layout.addWidget(self.loop_start_note)
        layout.addWidget(self.kept_note)
        layout.addWidget(self.buttons)

        self.fill_folders(selected=folder)

        self._name_changed(name)

    def _name_changed(self, text: str):
        self.ok_button.setEnabled(bool(text.strip()))
        self.kept_note.setVisible(text.strip() in self._kept_names)

    @classmethod
    def ask(
        cls,
        parent,
        favourites: Favourites,
        name: str,
        loops: int,
        loop_start: int | None = None,
        folder: FolderPath = (),
        kept_names: frozenset[str] = frozenset(),
        position: int | None = None,
    ):
        """(the favourites with any folders made, the folder picked, the
        name given), None for the viewer thinking better of it."""

        dialog = cls(
            favourites=favourites,
            name=name,
            loops=loops,
            loop_start=loop_start,
            folder=folder,
            kept_names=kept_names,
            position=position,
            parent=parent,
        )

        if not dialog.exec():
            return None

        name = dialog.name.text().strip()

        if not name:
            return None

        return dialog.favourites, dialog.selected_folder, name


class AddAllFavouritesDialog(_InFolderDialog):
    """All the videos open, or those picked out, made favourites, each under
    its own name, in a folder of the viewer's picking."""

    def __init__(
        self,
        favourites: Favourites,
        count: int,
        left_out: int,
        is_selected: bool = False,
        folder: FolderPath = (),
        **kwargs,
    ):
        super().__init__(favourites, **kwargs)

        if is_selected:
            self.setWindowTitle(translate("Favourites", "Add Selected to Favourites"))
        else:
            self.setWindowTitle(translate("Favourites", "Add All to Favourites"))

        self.count_note = QLabel(
            translate(
                "Favourites",
                "Videos to add: {COUNT}. Any already in your favourites are replaced.",
            ).format(COUNT=count_txt(count)),
            self,
        )
        self.count_note.setWordWrap(True)

        # streams and links, which favourites are not made of
        self.left_out_note = QLabel(
            translate("Favourites", "Left out, as not files on disk: {COUNT}").format(
                COUNT=count_txt(left_out)
            ),
            self,
        )
        self.left_out_note.setVisible(left_out > 0)

        form = QFormLayout()
        form.addRow(translate("Favourites", "Folder:"), self._folder_row())

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(self.count_note)
        layout.addWidget(self.left_out_note)
        layout.addWidget(self.buttons)

        self.fill_folders(selected=folder)

    @classmethod
    def ask(
        cls,
        parent,
        favourites: Favourites,
        count: int,
        left_out: int,
        is_selected: bool = False,
        folder: FolderPath = (),
    ):
        """(the favourites with any folders made, the folder picked), None
        for the viewer thinking better of it. The folder given picked to
        begin with."""

        dialog = cls(
            favourites=favourites,
            count=count,
            left_out=left_out,
            is_selected=is_selected,
            folder=folder,
            parent=parent,
        )

        if not dialog.exec():
            return None

        return dialog.favourites, dialog.selected_folder


class MoveToFolderDialog(QDialog):
    """The folder to move favourites into, picked from those of Manage
    Favourites as it shows them."""

    def __init__(self, folders: list, selected=None, **kwargs):
        super().__init__(**kwargs)

        self.setWindowTitle(translate("Favourites", "Move To Folder"))

        self.folder = _folder_box(self)

        for depth, title, tree_item in folders:
            _add_folder(self.folder, depth, title, tree_item)

        shown = [self.folder.itemData(i) for i in range(self.folder.count())]
        if selected in shown:
            self.folder.setCurrentIndex(shown.index(selected))

        buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel, Qt.Horizontal, self
        )
        buttons.button(QDialogButtonBox.Ok).setText(translate("Favourites", "Move"))
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        form = QFormLayout()
        form.addRow(translate("Favourites", "Folder:"), self.folder)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(buttons)

    @property
    def selected_folder(self):
        return self.folder.currentData()

    @classmethod
    def ask(cls, parent, folders: list, selected=None):
        """The tree item of the folder picked, the tree's own root for the
        top; None for the viewer thinking better of it."""

        dialog = cls(folders=folders, selected=selected, parent=parent)

        if not dialog.exec():
            return None

        return dialog.selected_folder


# how long the mouse rests on a video before it is shown moving
PREVIEW_DELAY_MS = 500
# how far from the mouse the box showing it is put
PREVIEW_OFFSET = QPoint(20, 20)


class HoverPreview(QLabel):
    """A box by the mouse showing a video moving: a frameless window of its
    own, over everything, taking neither the keys nor the mouse."""

    def __init__(self, parent=None):
        super().__init__(parent)

        self.setWindowFlags(Qt.ToolTip | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.setStyleSheet("background: black; border: 1px solid palette(mid);")
        self.setAlignment(Qt.AlignCenter)
        self.hide()

    def clear_frame(self):
        self.clear()

    def show_frame(self, pixmap, cursor: QPoint):
        self.setPixmap(pixmap)

        size = pixmap.size()
        if self.size() != size:
            self.resize(size)

        if not self.isVisible():
            self.move(self._place_by(cursor, size))
            self.show()

    def _place_by(self, cursor: QPoint, size) -> QPoint:
        """Below and to the right of the mouse; flipped to its other side
        where the screen ends."""

        place = cursor + PREVIEW_OFFSET

        screen = QApplication.screenAt(cursor)
        if screen is None:
            return place

        area = screen.availableGeometry()

        if place.x() + size.width() > area.right():
            place.setX(cursor.x() - PREVIEW_OFFSET.x() - size.width())
        if place.y() + size.height() > area.bottom():
            place.setY(cursor.y() - PREVIEW_OFFSET.y() - size.height())

        return place


# how strongly the row under the mouse is tinted with the colour picked
# rows have: enough to see, clearly not picked
HOVER_TINT_ALPHA = 60


class HoverTree(QTreeWidget):
    """A tree whose row under the mouse is tinted, all the way across."""

    def __init__(self, parent=None):
        super().__init__(parent)

        self._hovered = None

    @property
    def hovered_item(self):
        return self._hovered

    def set_hovered(self, tree_item) -> None:
        if tree_item is self._hovered:
            return

        self._hovered = tree_item
        self.viewport().update()

    def hover_color(self) -> QColor:
        color = QColor(self.palette().highlight().color())
        color.setAlpha(HOVER_TINT_ALPHA)
        return color

    def drawRow(self, painter, option, index):
        # one picked shows that it is, as it is
        if (
            self._hovered is not None
            and self.itemFromIndex(index) is self._hovered
            and not self._hovered.isSelected()
        ):
            painter.fillRect(option.rect, self.hover_color())

        super().drawRow(painter, option, index)


class ManageFavouritesDialog(QDialog):
    """The favourites as a tree, to be put in order: dragged into folders and
    about, or moved into a folder picked (Move To, in any sort), folders
    made, anything renamed or removed. Kept only on OK.

    A folder, or videos, opened from it into the grid as they are picked
    (Open, or a double click), the window staying for more, or closing as
    on OK (Open and Close): videos here, and a folder's own, those of each
    folder it holds in a new window each; several folders, each in a new
    window of its own.

    Shown in their own order, or sorted by name or by when they were added,
    each folder's own, the sort kept for the next time and the menu's too;
    their own order is the one kept on OK all the same. Dragged about only
    in it: sorted, there is no place to drop one in."""

    # the videos to open here, and the lists of them for new windows
    open_requested = pyqtSignal(list, list)

    def __init__(self, favourites: Favourites, **kwargs):
        super().__init__(**kwargs)

        self.setWindowTitle(translate("Favourites", "Manage Favourites"))
        self.resize(860, 440)

        self.tree = HoverTree(self)
        self.tree.setColumnCount(5)
        self.tree.setHeaderLabels(
            [
                translate("Favourites", "Name"),
                translate("Favourites", "A-B Loops"),
                translate("Favourites", "Opens At"),
                translate("Favourites", "File"),
                translate("Favourites", "Date Added"),
            ]
        )
        self.tree.header().setSectionResizeMode(0, QHeaderView.Interactive)
        self.tree.header().resizeSection(0, 260)
        self.tree.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.tree.setDragDropMode(QAbstractItemView.InternalMove)
        self.tree.setDefaultDropAction(Qt.MoveAction)
        self.tree.setEditTriggers(
            QAbstractItemView.EditKeyPressed | QAbstractItemView.SelectedClicked
        )

        self.new_folder_button = QPushButton(
            QIcon.fromTheme("favourites-folder"),
            translate("Favourites", "New Folder..."),
            self,
        )
        self.new_folder_button.clicked.connect(self.new_folder)

        self.rename_button = QPushButton(translate("Favourites", "Rename"), self)
        self.rename_button.clicked.connect(self.rename_selected)

        self.remove_button = QPushButton(translate("Favourites", "Remove"), self)
        self.remove_button.clicked.connect(self.remove_selected)

        self.move_button = QPushButton(translate("Favourites", "Move To..."), self)
        self.move_button.clicked.connect(self.move_selected)

        self.open_button = QPushButton(
            QIcon.fromTheme("add-files"), translate("Favourites", "Open"), self
        )
        self.open_button.clicked.connect(self.open_selected)
        self.tree.itemDoubleClicked.connect(lambda item, _: self._open([item]))

        # the video under the mouse shown moving, a moment after it rests
        # on it, in a box beside it
        self.tree.setMouseTracking(True)
        self.tree.itemEntered.connect(self._hovered)
        self.tree.viewport().installEventFilter(self)
        self.tree.verticalScrollBar().valueChanged.connect(self.stop_preview)

        self._previewer = None
        self._preview = HoverPreview(self)
        self._preview_item = None
        self._preview_timer = QTimer(self)
        self._preview_timer.setSingleShot(True)
        self._preview_timer.setInterval(PREVIEW_DELAY_MS)
        self._preview_timer.timeout.connect(self._show_preview)

        QShortcut(QKeySequence.Delete, self.tree, self.remove_selected)

        self.sort_box = QComboBox(self)
        self.sort_box.setSizeAdjustPolicy(QComboBox.AdjustToContents)
        for sort, title in (
            (FavouritesSort.OWN, translate("Favourites", "Your Order")),
            (FavouritesSort.NAME, translate("Favourites", "Name (A to Z)")),
            (FavouritesSort.NAME_DESC, translate("Favourites", "Name (Z to A)")),
            (
                FavouritesSort.ADDED_DESC,
                translate("Favourites", "Date Added (Newest First)"),
            ),
            (
                FavouritesSort.ADDED,
                translate("Favourites", "Date Added (Oldest First)"),
            ),
        ):
            self.sort_box.addItem(title, sort)

        sort_label = QLabel(translate("Favourites", "Sort by:"), self)
        sort_label.setBuddy(self.sort_box)

        buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel, Qt.Horizontal, self
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        # opens those picked, then closes as OK does, the changes kept
        self.open_close_button = buttons.addButton(
            translate("Favourites", "Open and Close"), QDialogButtonBox.ActionRole
        )
        self.open_close_button.setIcon(QIcon.fromTheme("add-files"))
        self.open_close_button.clicked.connect(self.open_selected_and_close)

        actions = QHBoxLayout()
        actions.addWidget(self.open_button)
        actions.addWidget(self.new_folder_button)
        actions.addWidget(self.rename_button)
        actions.addWidget(self.move_button)
        actions.addWidget(self.remove_button)
        actions.addStretch(1)
        actions.addWidget(sort_label)
        actions.addWidget(self.sort_box)

        layout = QVBoxLayout(self)
        layout.addWidget(self.tree, 1)
        layout.addLayout(actions)
        layout.addWidget(buttons)

        self.tree.itemSelectionChanged.connect(self._update_buttons)
        self.tree.itemChanged.connect(self._renamed)

        self.sort = FavouritesSort.OWN
        # the next place in the folders' own order, for one made while sorted
        self._next_order = 0
        self._is_sorting = False

        self._fill(self.tree.invisibleRootItem(), favourites.root)
        self.tree.expandAll()
        self._update_buttons()

        # one moved, made or removed: the folders dated again, and placed
        # again sorted by date
        self._is_refresh_due = False
        self.tree.model().rowsInserted.connect(self._contents_changed)
        self.tree.model().rowsRemoved.connect(self._contents_changed)

        sort = Settings().get("favourites/sort")
        self.sort_box.setCurrentIndex(max(self.sort_box.findData(sort), 0))
        self.sort_by(self.sort_box.currentData())
        self.sort_box.currentIndexChanged.connect(
            lambda _: self._sort_picked(self.sort_box.currentData())
        )

    # the tree

    def _fill(self, parent_item, items):
        for item in items:
            if isinstance(item, FavouriteFolder):
                tree_item = self._folder_item(item.name, item.added)
                parent_item.addChild(tree_item)
                self._fill(tree_item, item.items)
            else:
                parent_item.addChild(self._video_item(item))

    def _folder_item(self, name: str, added) -> QTreeWidgetItem:
        tree_item = QTreeWidgetItem([name, "", "", "", _added_txt(added)])
        tree_item.setIcon(0, QIcon.fromTheme("favourites-folder"))
        tree_item.setData(0, ITEM_ADDED, added)
        tree_item.setFlags(
            Qt.ItemIsEnabled
            | Qt.ItemIsSelectable
            | Qt.ItemIsEditable
            | Qt.ItemIsDragEnabled
            | Qt.ItemIsDropEnabled
        )
        return tree_item

    def _video_item(self, video: FavouriteVideo) -> QTreeWidgetItem:
        loops = [count_txt(len(video.loops))] if video.loops else []
        loops.extend(
            _loop_start_txt(start)
            for start in (*video.earlier_loop_starts, video.loop_start)
            if start is not None
        )

        opens_at = (
            "" if video.position is None else ms_time_txt(video.position, strip=True)
        )

        tree_item = QTreeWidgetItem(
            [
                video.name,
                ", ".join(loops),
                opens_at,
                str(video.path),
                _added_txt(video.added),
            ]
        )
        tree_item.setIcon(0, QIcon.fromTheme("add-files"))
        tree_item.setToolTip(3, str(video.path))
        tree_item.setData(0, ITEM_FAVOURITE, video)
        # nothing is dropped into a video, only next to it
        tree_item.setFlags(
            Qt.ItemIsEnabled
            | Qt.ItemIsSelectable
            | Qt.ItemIsEditable
            | Qt.ItemIsDragEnabled
        )
        return tree_item

    def favourites(self) -> Favourites:
        """The favourites as the tree has them now."""

        return Favourites(self._read(self.tree.invisibleRootItem()))

    def _read(self, parent_item, is_as_shown: bool = False) -> list:
        """A folder's, in their own order, or as shown."""

        items = []

        for tree_item in self._children(parent_item, is_as_shown):
            name = tree_item.text(0).strip()
            video = tree_item.data(0, ITEM_FAVOURITE)

            if video is None:
                items.append(
                    FavouriteFolder(
                        name=name or translate("Favourites", "New Folder"),
                        items=self._read(tree_item, is_as_shown),
                        added=tree_item.data(0, ITEM_ADDED),
                    )
                )
            else:
                items.append(video.model_copy(update={"name": name or video.name}))

        return items

    def _children(self, parent_item, is_as_shown: bool = False) -> list:
        children = [parent_item.child(i) for i in range(parent_item.childCount())]

        if is_as_shown or self.sort == FavouritesSort.OWN:
            return children

        return sorted(children, key=lambda child: child.data(0, ITEM_ORDER))

    def _to_open(self, tree_items) -> tuple[list, list[list]]:
        """What the ones picked open, in the order shown: here, a video
        itself, and a folder's own videos, as Open All of its menu opens;
        in a new window each, the videos of each folder a folder picked
        holds. Several folders picked, each its own in a new window too, a
        window each, the videos picked still here. One within a folder
        picked goes with that folder."""

        picked = {id(tree_item) for tree_item in tree_items}
        here, apart = [], []

        def is_within_picked(tree_item):
            parent = tree_item.parent()
            while parent is not None:
                if id(parent) in picked:
                    return True
                parent = parent.parent()
            return False

        is_each_apart = (
            sum(
                1
                for tree_item in tree_items
                if tree_item.data(0, ITEM_FAVOURITE) is None
                and not is_within_picked(tree_item)
            )
            > 1
        )

        def walk(parent_item):
            for index in range(parent_item.childCount()):
                tree_item = parent_item.child(index)
                is_folder = tree_item.data(0, ITEM_FAVOURITE) is None

                if id(tree_item) in picked and not is_within_picked(tree_item):
                    if is_folder:
                        items = self._read(tree_item, is_as_shown=True)
                        own = videos_in(items)
                        if not is_each_apart:
                            here.extend(own)
                        elif own:
                            apart.append(own)
                        apart.extend(folders_within(items))
                    else:
                        here.append(self._read_video(tree_item))

                if is_folder:
                    walk(tree_item)

        walk(self.tree.invisibleRootItem())

        return here, apart

    def _read_video(self, tree_item) -> FavouriteVideo:
        video = tree_item.data(0, ITEM_FAVOURITE)
        name = tree_item.text(0).strip()
        return video.model_copy(update={"name": name or video.name})

    def open_selected(self):
        self._open(self.tree.selectedItems())

    def open_selected_and_close(self):
        if not any(self._to_open(self.tree.selectedItems())):
            return

        self.open_selected()
        self.accept()

    def _open(self, tree_items):
        here, apart = self._to_open(tree_items)

        if here or apart:
            self.open_requested.emit(here, apart)

    # the video under the mouse shown moving

    def _hovered(self, tree_item, _column=0):
        # the row under the mouse marked, whatever it is
        self.tree.set_hovered(tree_item)

        video = tree_item.data(0, ITEM_FAVOURITE)

        if video is None or tree_item is self._preview_item:
            if video is None:
                self.stop_preview()
            return

        self.stop_preview()

        # not while one is dragged about, or for a file that is gone
        if QApplication.mouseButtons() != Qt.NoButton:
            return
        if not Path(video.path).is_file():
            return

        self._preview_item = tree_item
        self._preview_timer.start()

        # started meanwhile, for it to be ready once the mouse has rested
        self._clip_previewer().warm_up()

    def _show_preview(self):
        self._preview_timer.stop()
        tree_item = self._preview_item

        if tree_item is None or tree_item.treeWidget() is not self.tree:
            return

        path = Path(tree_item.data(0, ITEM_FAVOURITE).path)
        previewer = self._clip_previewer()

        if not previewer.is_readable(path) or not previewer.play(path):
            self._preview_item = None
            return

        self._preview.clear_frame()

    def _clip_previewer(self):
        if self._previewer is None:
            from gridplayer.utils.clip_preview import ClipPreviewer

            self._previewer = ClipPreviewer(self)
            self._previewer.frame.connect(self._on_preview_frame)
            self._previewer.failed.connect(self.stop_preview)

        return self._previewer

    def _on_preview_frame(self, image):
        if self._preview_item is None:
            return

        self._preview.show_frame(QPixmap.fromImage(image), QCursor.pos())

    def stop_preview(self, *_):
        self._preview_timer.stop()
        self._preview_item = None
        self._preview.hide()

        if self._previewer is not None:
            self._previewer.stop()

    def eventFilter(self, watched, event):
        if watched is self.tree.viewport() and event.type() in {
            QEvent.Leave,
            QEvent.MouseButtonPress,
            QEvent.Wheel,
        }:
            self.stop_preview()

            # the rows move under the mouse as they scroll: marked again
            # as it next moves
            if event.type() != QEvent.MouseButtonPress:
                self.tree.set_hovered(None)

        return super().eventFilter(watched, event)

    def done(self, result):
        self.stop_preview()

        if self._previewer is not None:
            self._previewer.close()
            self._previewer = None

        super().done(result)

    # sorted

    def _sort_picked(self, sort: FavouritesSort):
        Settings().set("favourites/sort", sort)
        self.sort_by(sort)

    def sort_by(self, sort: FavouritesSort):
        """Shown sorted so, each folder's own; their own order, taken from
        the tree while it shows it, put back for OWN."""

        if self.sort == FavouritesSort.OWN:
            self._number_own_order(self.tree.invisibleRootItem())

        self.sort = sort

        self.tree.setDragDropMode(
            QAbstractItemView.InternalMove
            if sort == FavouritesSort.OWN
            else QAbstractItemView.NoDragDrop
        )

        self._sort_all(self.tree.invisibleRootItem())

    def _number_own_order(self, parent_item):
        for index in range(parent_item.childCount()):
            tree_item = parent_item.child(index)
            self._is_sorting = True
            tree_item.setData(0, ITEM_ORDER, self._take_order())
            self._is_sorting = False
            self._number_own_order(tree_item)

    def _take_order(self) -> int:
        self._next_order += 1
        return self._next_order

    def _show_folder_dates(self):
        """Each folder dated by the latest within it, as it is sorted."""

        for tree_item in _all_within(self.tree.invisibleRootItem()):
            if tree_item.data(0, ITEM_FAVOURITE) is None:
                tree_item.setText(COLUMN_ADDED, _added_txt(_added_of(tree_item)))

    def _contents_changed(self, *_):
        if self._is_sorting or self._is_refresh_due:
            return

        self._is_refresh_due = True
        QTimer.singleShot(0, self._refresh)

    def _refresh(self):
        self._is_refresh_due = False

        if self.sort in {FavouritesSort.ADDED, FavouritesSort.ADDED_DESC}:
            self._sort_all(self.tree.invisibleRootItem())
        else:
            self._show_folder_dates()

    def _sort_all(self, parent_item):
        self._show_folder_dates()
        self._sort_tree(parent_item)

    def _sort_tree(self, parent_item):
        self._sort_children(parent_item)

        for index in range(parent_item.childCount()):
            self._sort_tree(parent_item.child(index))

    def _sort_children(self, parent_item):
        shown = [parent_item.child(i) for i in range(parent_item.childCount())]
        children = sorted(shown, key=lambda child: child.data(0, ITEM_ORDER))

        children = sorted_by(
            children,
            self.sort,
            name_of=lambda child: child.text(0),
            added_of=_added_of,
        )

        if children == shown:
            return

        # taken out and put back, they forget being open and picked
        within = _all_within(parent_item)
        expanded = [item for item in within if item.isExpanded()]
        selected = [item for item in within if item.isSelected()]
        current = self.tree.currentItem()

        self._is_sorting = True
        parent_item.takeChildren()
        parent_item.addChildren(children)
        self._is_sorting = False

        for item in expanded:
            item.setExpanded(True)
        if current in within:
            self.tree.setCurrentItem(current, 0, QItemSelectionModel.NoUpdate)
        for item in selected:
            item.setSelected(True)

    def _renamed(self, tree_item, column: int):
        """One renamed is put where its new name goes, once its editor has
        closed."""

        if self._is_sorting or column != 0:
            return

        if self.sort not in {FavouritesSort.NAME, FavouritesSort.NAME_DESC}:
            return

        QTimer.singleShot(0, lambda: self._resort_around(tree_item))

    def _resort_around(self, tree_item):
        if tree_item.treeWidget() is not self.tree:
            return

        self._sort_children(tree_item.parent() or self.tree.invisibleRootItem())
        self.tree.scrollToItem(tree_item)

    # what is done to it

    def _update_buttons(self):
        selected = self.tree.selectedItems()

        self.rename_button.setEnabled(len(selected) == 1)
        self.remove_button.setEnabled(bool(selected))
        self.move_button.setEnabled(bool(selected))
        is_any_to_open = any(self._to_open(selected))
        self.open_button.setEnabled(is_any_to_open)
        self.open_close_button.setEnabled(is_any_to_open)

    def _new_folder_parent(self):
        """Where a new folder goes: into the folder picked, beside the video
        picked, at the top with nothing picked."""

        current = self.tree.currentItem()

        if current is None or not current.isSelected():
            return self.tree.invisibleRootItem()

        if current.data(0, ITEM_FAVOURITE) is None:
            return current

        return current.parent() or self.tree.invisibleRootItem()

    def new_folder(self):
        name = _new_folder_name(self)

        if name is None:
            return

        parent_item = self._new_folder_parent()

        tree_item = self._folder_item(name, added_now())
        tree_item.setData(0, ITEM_ORDER, self._take_order())
        parent_item.addChild(tree_item)
        parent_item.setExpanded(True)
        if self.sort != FavouritesSort.OWN:
            self._sort_children(parent_item)

        self.tree.setCurrentItem(tree_item)

    def rename_selected(self):
        selected = self.tree.selectedItems()

        if len(selected) == 1:
            self.tree.editItem(selected[0], 0)

    def remove_selected(self):
        selected = self.tree.selectedItems()

        if not self._is_removing_sure(selected):
            return

        for tree_item in selected:
            parent_item = tree_item.parent() or self.tree.invisibleRootItem()
            parent_item.removeChild(tree_item)

    def _moved_ones(self) -> list:
        """Those picked, in the order shown, but those within a folder
        picked, which go with it."""

        picked = {id(tree_item) for tree_item in self.tree.selectedItems()}

        def is_within_picked(tree_item):
            parent = tree_item.parent()
            while parent is not None:
                if id(parent) in picked:
                    return True
                parent = parent.parent()
            return False

        return [
            tree_item
            for tree_item in _all_within(self.tree.invisibleRootItem())
            if id(tree_item) in picked and not is_within_picked(tree_item)
        ]

    def _folders_to_move_into(self, moved: list) -> list:
        """(depth, title, tree item) of each folder, the top first, as
        shown; but those moved and those within them, which cannot hold
        themselves."""

        moved_ids = {id(tree_item) for tree_item in moved}
        root = self.tree.invisibleRootItem()
        folders = [(0, translate("Favourites", "Favourites"), root)]

        def walk(parent_item, depth):
            for index in range(parent_item.childCount()):
                tree_item = parent_item.child(index)

                if tree_item.data(0, ITEM_FAVOURITE) is not None:
                    continue
                if id(tree_item) in moved_ids:
                    continue

                folders.append((depth, tree_item.text(0).strip(), tree_item))
                walk(tree_item, depth + 1)

        walk(root, 1)

        return folders

    def move_selected(self):
        """Those picked moved into a folder of the viewer's picking, at the
        end of its own order, whatever it is shown sorted by."""

        moved = self._moved_ones()

        if not moved:
            return

        parents = {
            id(tree_item.parent() or self.tree.invisibleRootItem())
            for tree_item in moved
        }
        first_parent = moved[0].parent() or self.tree.invisibleRootItem()

        target = MoveToFolderDialog.ask(
            parent=self,
            folders=self._folders_to_move_into(moved),
            # where they are, when all are in one folder
            selected=first_parent if len(parents) == 1 else None,
        )

        if target is None:
            return

        self.move_into(moved, target)

    def move_into(self, moved: list, target) -> None:
        within = _all_within(self.tree.invisibleRootItem())
        expanded = [item for item in within if item.isExpanded()]

        for tree_item in moved:
            parent_item = tree_item.parent() or self.tree.invisibleRootItem()

            if parent_item is target:
                continue

            parent_item.removeChild(tree_item)
            tree_item.setData(0, ITEM_ORDER, self._take_order())
            target.addChild(tree_item)

        for item in expanded:
            item.setExpanded(True)
        target.setExpanded(True)

        if self.sort != FavouritesSort.OWN:
            self._sort_children(target)

        self.tree.clearSelection()
        for tree_item in moved:
            tree_item.setSelected(True)
        self.tree.setCurrentItem(moved[0], 0, QItemSelectionModel.NoUpdate)
        self.tree.scrollToItem(moved[0])

    def _is_removing_sure(self, selected) -> bool:
        """Asked first when a folder is among them, as all it holds goes
        with it; videos alone go without asking."""

        folders = [i for i in selected if i.data(0, ITEM_FAVOURITE) is None]

        if not folders:
            return True

        if len(folders) == 1:
            question = translate(
                "Favourites", 'Remove the folder "{NAME}" and everything in it?'
            ).format(NAME=folders[0].text(0).strip())
        else:
            question = translate(
                "Favourites", "Remove {COUNT} folders and everything in them?"
            ).format(COUNT=count_txt(len(folders)))

        answer = QCustomMessageBox.question(
            self, translate("Favourites", "Remove"), question
        )

        return answer == QMessageBox.Yes

    @classmethod
    def edit(cls, parent, favourites: Favourites, on_open=None) -> Favourites | None:
        dialog = cls(favourites=favourites, parent=parent)

        if on_open is not None:
            dialog.open_requested.connect(on_open)

        if dialog.exec():
            return dialog.favourites()

        return None
