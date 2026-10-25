"""The favourites' windows, as a web browser has them: one to make the active
video a favourite, in a folder of the viewer's picking, and one to put them
in order, in folders made, renamed, moved about and removed."""

from PyQt5.QtCore import Qt
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
)
from gridplayer.utils.qt import count_txt, translate
from gridplayer.utils.time_txt import ms_time_txt

FOLDER_INDENT = "    "

# what an item of the tree is: a video's favourite, or nothing for a folder
ITEM_FAVOURITE = Qt.UserRole


def _loop_start_txt(loop_start: int) -> str:
    return translate("Favourites", "start at {TIME}").format(
        TIME=ms_time_txt(loop_start, strip=True)
    )


def _new_folder_name(parent) -> str | None:
    name = QCustomTextInput.get_text(
        parent,
        translate("Favourites", "New Folder"),
        placeholder=translate("Favourites", "Folder name"),
    )

    name = (name or "").strip()

    return name or None


def imported_folder_name(parent, name: str) -> str | None:
    """The name of the folder a playlist imported goes in, as the viewer
    leaves or changes it; None for the viewer thinking better of it."""

    dialog = QCustomTextInput(parent=parent)
    dialog.setWindowTitle(translate("Favourites", "Import Playlist: Folder Name"))
    dialog.line_edit.setText(name)
    dialog.line_edit.selectAll()
    dialog.line_edit.setPlaceholderText(translate("Favourites", "Folder name"))

    if not dialog.exec():
        return None

    return dialog.line_edit.text().strip() or None


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
        self.favourites.add(parent, FavouriteFolder(name=name))

        new_path = (*parent, len(self.favourites.items_at(parent)) - 1)
        self.fill_folders(selected=new_path)


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
    about, folders made, anything renamed or removed. Kept only on OK."""

    def __init__(self, favourites: Favourites, **kwargs):
        super().__init__(**kwargs)

        self.setWindowTitle(translate("Favourites", "Manage Favourites"))
        self.resize(640, 420)

        self.tree = QTreeWidget(self)
        self.tree.setColumnCount(4)
        self.tree.setHeaderLabels(
            [
                translate("Favourites", "Name"),
                translate("Favourites", "A-B Loops"),
                translate("Favourites", "Opens At"),
                translate("Favourites", "File"),
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

        QShortcut(QKeySequence.Delete, self.tree, self.remove_selected)

        buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel, Qt.Horizontal, self
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        actions = QHBoxLayout()
        actions.addWidget(self.new_folder_button)
        actions.addWidget(self.rename_button)
        actions.addWidget(self.remove_button)
        actions.addStretch(1)

        layout = QVBoxLayout(self)
        layout.addWidget(self.tree, 1)
        layout.addLayout(actions)
        layout.addWidget(buttons)

        self.tree.itemSelectionChanged.connect(self._update_buttons)

        self._fill(self.tree.invisibleRootItem(), favourites.root)
        self.tree.expandAll()
        self._update_buttons()

    # the tree

    def _fill(self, parent_item, items):
        for item in items:
            if isinstance(item, FavouriteFolder):
                tree_item = self._folder_item(item.name)
                parent_item.addChild(tree_item)
                self._fill(tree_item, item.items)
            else:
                parent_item.addChild(self._video_item(item))

    def _folder_item(self, name: str) -> QTreeWidgetItem:
        tree_item = QTreeWidgetItem([name, "", "", ""])
        tree_item.setIcon(0, QIcon.fromTheme("favourites-folder"))
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
            [video.name, ", ".join(loops), opens_at, str(video.path)]
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

        def read(parent_item):
            items = []

            for index in range(parent_item.childCount()):
                tree_item = parent_item.child(index)
                name = tree_item.text(0).strip()
                video = tree_item.data(0, ITEM_FAVOURITE)

                if video is None:
                    items.append(
                        FavouriteFolder(
                            name=name or translate("Favourites", "New Folder"),
                            items=read(tree_item),
                        )
                    )
                else:
                    items.append(video.model_copy(update={"name": name or video.name}))

            return items

        return Favourites(read(self.tree.invisibleRootItem()))

    # what is done to it

    def _update_buttons(self):
        selected = self.tree.selectedItems()

        self.rename_button.setEnabled(len(selected) == 1)
        self.remove_button.setEnabled(bool(selected))

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

        tree_item = self._folder_item(name)
        parent_item.addChild(tree_item)
        parent_item.setExpanded(True)

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
    def edit(cls, parent, favourites: Favourites) -> Favourites | None:
        dialog = cls(favourites=favourites, parent=parent)

        if dialog.exec():
            return dialog.favourites()

        return None
