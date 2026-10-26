"""The favourites' windows, as a web browser has them: one to make the active
video a favourite, in a folder of the viewer's picking, and one to put them
in order, in folders made, renamed, moved about and removed."""

from math import inf

from PyQt5.QtCore import (
    QDateTime,
    QItemSelectionModel,
    QLocale,
    Qt,
    QTimer,
    pyqtSignal,
)
from PyQt5.QtGui import QIcon, QKeySequence
from PyQt5.QtWidgets import (
    QAbstractItemView,
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
    videos_in,
)
from gridplayer.params.static import FavouritesSort
from gridplayer.settings import Settings
from gridplayer.utils.next_file import natural_key
from gridplayer.utils.qt import count_txt, translate
from gridplayer.utils.time_txt import ms_time_txt

FOLDER_INDENT = "    "

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
    video = tree_item.data(0, ITEM_FAVOURITE)
    return tree_item.data(0, ITEM_ADDED) if video is None else video.added


def _added_key(added) -> float:
    return -inf if added is None else added.timestamp()


def _all_within(parent_item) -> list:
    found = []

    for index in range(parent_item.childCount()):
        child = parent_item.child(index)
        found.append(child)
        found.extend(_all_within(child))

    return found


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

        self.folder = QComboBox(self)
        self.folder.setMinimumWidth(320)

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
            self.folder.addItem(
                QIcon.fromTheme("favourites-folder"),
                FOLDER_INDENT * len(path) + title,
                path,
            )

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

    def __init__(self, favourites: Favourites, names: list[str], **kwargs):
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

        self.fill_folders()

    @property
    def names(self) -> list[str]:
        if self.name is None:
            return list(self._names)

        return [self.name.text().strip()]

    @classmethod
    def ask(cls, parent, favourites: Favourites, names: list[str]):
        """(the favourites with any folders made, the folder picked, the
        names of the folders the playlists go in), None for the viewer
        thinking better of it."""

        dialog = cls(favourites=favourites, names=names, parent=parent)

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

        self.fill_folders()

    @classmethod
    def ask(
        cls,
        parent,
        favourites: Favourites,
        count: int,
        left_out: int,
        is_selected: bool = False,
    ):
        """(the favourites with any folders made, the folder picked), None
        for the viewer thinking better of it."""

        dialog = cls(
            favourites=favourites,
            count=count,
            left_out=left_out,
            is_selected=is_selected,
            parent=parent,
        )

        if not dialog.exec():
            return None

        return dialog.favourites, dialog.selected_folder


class ManageFavouritesDialog(QDialog):
    """The favourites as a tree, to be put in order: dragged into folders and
    about, folders made, anything renamed or removed. Kept only on OK.

    A folder, or videos, opened from it into the grid as they are picked
    (Open, or a double click), the window staying for more: a folder's
    own videos here, those of each folder it holds in a new window each.

    Shown in their own order, or sorted by name or by when they were added,
    each folder's own, the sort kept for the next time; their own order is
    the one kept on OK all the same, and the menu's. Dragged about only in
    it: sorted, there is no place to drop one in."""

    # the videos to open here, and the lists of them for new windows
    open_requested = pyqtSignal(list, list)

    def __init__(self, favourites: Favourites, **kwargs):
        super().__init__(**kwargs)

        self.setWindowTitle(translate("Favourites", "Manage Favourites"))
        self.resize(860, 440)

        self.tree = QTreeWidget(self)
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

        self.open_button = QPushButton(
            QIcon.fromTheme("add-files"), translate("Favourites", "Open"), self
        )
        self.open_button.clicked.connect(self.open_selected)
        self.tree.itemDoubleClicked.connect(lambda item, _: self._open([item]))

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

        actions = QHBoxLayout()
        actions.addWidget(self.open_button)
        actions.addWidget(self.new_folder_button)
        actions.addWidget(self.rename_button)
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
        if video.loop_start is not None:
            loops.append(_loop_start_txt(video.loop_start))

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
        """What the ones picked open, in the order shown: here, a folder's
        own videos, as Open All of its menu opens, and a video itself; in a
        new window each, the videos of each folder a folder picked holds.
        One within a folder picked goes with that folder."""

        picked = {id(tree_item) for tree_item in tree_items}
        here, apart = [], []

        def is_within_picked(tree_item):
            parent = tree_item.parent()
            while parent is not None:
                if id(parent) in picked:
                    return True
                parent = parent.parent()
            return False

        def walk(parent_item):
            for index in range(parent_item.childCount()):
                tree_item = parent_item.child(index)
                is_folder = tree_item.data(0, ITEM_FAVOURITE) is None

                if id(tree_item) in picked and not is_within_picked(tree_item):
                    if is_folder:
                        items = self._read(tree_item, is_as_shown=True)
                        here.extend(videos_in(items))
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

    def _open(self, tree_items):
        here, apart = self._to_open(tree_items)

        if here or apart:
            self.open_requested.emit(here, apart)

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

    def _sort_all(self, parent_item):
        self._sort_children(parent_item)

        for index in range(parent_item.childCount()):
            self._sort_all(parent_item.child(index))

    def _sort_children(self, parent_item):
        shown = [parent_item.child(i) for i in range(parent_item.childCount())]
        children = sorted(shown, key=lambda child: child.data(0, ITEM_ORDER))

        if self.sort in {FavouritesSort.NAME, FavouritesSort.NAME_DESC}:
            children.sort(
                key=lambda child: natural_key(child.text(0).strip()),
                reverse=self.sort == FavouritesSort.NAME_DESC,
            )
        elif self.sort in {FavouritesSort.ADDED, FavouritesSort.ADDED_DESC}:
            # one added before favourites kept it as the oldest; one added at
            # the same time as another kept in their own order, which a
            # reversed sort keeps too
            children.sort(
                key=lambda child: _added_key(_added_of(child)),
                reverse=self.sort == FavouritesSort.ADDED_DESC,
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
        self.open_button.setEnabled(any(self._to_open(selected)))

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
