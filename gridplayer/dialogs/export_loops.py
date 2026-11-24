"""What exporting a video's loops is to make: where to, how long each fades
into the next, in what order, and how good (see utils.loop_export)."""

from dataclasses import dataclass
from pathlib import Path

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QButtonGroup,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QRadioButton,
    QVBoxLayout,
    QWidget,
)

from gridplayer.utils.loop_export import (
    AllMode,
    ExportQuality,
    LoopOrder,
    OutputSize,
)
from gridplayer.utils.qt import translate

# the longest fade asked for, in seconds
MAX_FADE_S = 5.0


@dataclass(frozen=True)
class ExportOptions:
    target: Path
    fade_s: float
    order: LoopOrder
    quality: ExportQuality


def _common_editors(parent, fade_s: float, order: LoopOrder, quality: ExportQuality):
    """The fade, the order and the quality, as both windows ask them."""

    fade = QDoubleSpinBox(parent)
    fade.setRange(0.0, MAX_FADE_S)
    fade.setSingleStep(0.25)
    fade.setDecimals(2)
    fade.setSuffix(" s")
    fade.setValue(fade_s)
    fade.setSpecialValueText(translate("Dialog - Export Loops", "No fade"))

    order_box = QComboBox(parent)
    for value, title in (
        (
            LoopOrder.TIMELINE,
            translate("Dialog - Export Loops", "As they come in the video"),
        ),
        (
            LoopOrder.MADE,
            translate("Dialog - Export Loops", "As they were made"),
        ),
    ):
        order_box.addItem(title, value)
    order_box.setCurrentIndex(max(order_box.findData(order), 0))

    quality_box = QComboBox(parent)
    for value, title in (
        (ExportQuality.HIGH, translate("Dialog - Export Loops", "High")),
        (ExportQuality.MEDIUM, translate("Dialog - Export Loops", "Medium")),
        (ExportQuality.SMALL, translate("Dialog - Export Loops", "Small file")),
    ):
        quality_box.addItem(title, value)
    quality_box.setCurrentIndex(max(quality_box.findData(quality), 0))

    return fade, order_box, quality_box


class ExportLoopsDialog(QDialog):
    def __init__(
        self,
        target: Path,
        loop_count: int,
        fade_s: float,
        order: LoopOrder,
        quality: ExportQuality,
        **kwargs,
    ):
        super().__init__(**kwargs)

        self.setWindowTitle(translate("Dialog - Export Loops", "Export Loops"))

        self.target = QLineEdit(str(target), self)
        self.target.setMinimumWidth(360)
        self.target.textChanged.connect(self._update_ok)

        self.browse_button = QPushButton(
            translate("Dialog - Export Loops", "Browse..."), self
        )
        self.browse_button.clicked.connect(self.browse)

        target_row = QHBoxLayout()
        target_row.addWidget(self.target, 1)
        target_row.addWidget(self.browse_button)

        self.fade, self.order, self.quality = _common_editors(
            self, fade_s, order, quality
        )

        form = QFormLayout()
        form.addRow(translate("Dialog - Export Loops", "Save as:"), target_row)
        form.addRow(
            translate("Dialog - Export Loops", "Fade between loops:"), self.fade
        )
        form.addRow(translate("Dialog - Export Loops", "Order:"), self.order)
        form.addRow(translate("Dialog - Export Loops", "Quality:"), self.quality)

        self.count_note = QLabel(
            translate(
                "Dialog - Export Loops",
                "Loops to export: {COUNT}, one after another, into one video.",
            ).format(COUNT=loop_count),
            self,
        )
        self.count_note.setWordWrap(True)

        self.buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel, Qt.Horizontal, self
        )
        self.ok_button = self.buttons.button(QDialogButtonBox.Ok)
        self.ok_button.setText(translate("Dialog - Export Loops", "Export"))
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(self.count_note)
        layout.addWidget(self.buttons)

        self._update_ok()

    def browse(self):
        path, _ = QFileDialog.getSaveFileName(
            self,
            translate("Dialog - Export Loops", "Export Loops"),
            self.target.text(),
            "{} (*.mp4)".format(translate("Dialog - Export Loops", "MP4 video")),
        )

        if path:
            self.target.setText(path)

    def _update_ok(self):
        self.ok_button.setEnabled(bool(self.target.text().strip()))

    def options(self) -> ExportOptions:
        target = Path(self.target.text().strip())

        if target.suffix.lower() != ".mp4":
            target = target.with_name(target.name + ".mp4")

        return ExportOptions(
            target=target,
            fade_s=self.fade.value(),
            order=self.order.currentData(),
            quality=self.quality.currentData(),
        )

    @classmethod
    def ask(cls, parent, **kwargs) -> ExportOptions | None:
        dialog = cls(parent=parent, **kwargs)

        if not dialog.exec():
            return None

        return dialog.options()


@dataclass(frozen=True)
class ExportAllOptions:
    mode: AllMode
    # EACH: the folder they go in, None for beside each video
    folder: Path | None
    # ONE: the file they all go in
    target: Path
    size: OutputSize
    fade_s: float
    order: LoopOrder
    quality: ExportQuality


class ExportAllLoopsDialog(QDialog):
    """The loops of every video in the grid, or of those picked out,
    exported: each video's into a file of its own, or all of them into
    one."""

    def __init__(
        self,
        target: Path,
        video_count: int,
        loop_count: int,
        left_out: int,
        mode: AllMode,
        size: OutputSize,
        fade_s: float,
        order: LoopOrder,
        quality: ExportQuality,
        **kwargs,
    ):
        super().__init__(**kwargs)

        self.setWindowTitle(
            translate("Dialog - Export Loops", "Export Loops of All Videos")
        )

        self.each_button = QRadioButton(
            translate("Dialog - Export Loops", "A video file for each"), self
        )
        self.one_button = QRadioButton(
            translate("Dialog - Export Loops", "One video of them all"), self
        )
        # two choices apart: what is made, and where each goes
        self._mode_group = QButtonGroup(self)
        self._mode_group.addButton(self.each_button)
        self._mode_group.addButton(self.one_button)
        (self.each_button if mode == AllMode.EACH else self.one_button).setChecked(True)

        # each: beside each video, or in a folder picked
        self.beside_button = QRadioButton(
            translate("Dialog - Export Loops", "Next to each video"), self
        )
        self.in_folder_button = QRadioButton(
            translate("Dialog - Export Loops", "In this folder:"), self
        )
        self._where_group = QButtonGroup(self)
        self._where_group.addButton(self.beside_button)
        self._where_group.addButton(self.in_folder_button)
        self.beside_button.setChecked(True)

        self.folder = QLineEdit(str(target.parent), self)
        self.folder_browse = QPushButton(
            translate("Dialog - Export Loops", "Browse..."), self
        )
        self.folder_browse.clicked.connect(self.browse_folder)

        folder_row = QHBoxLayout()
        folder_row.addWidget(self.in_folder_button)
        folder_row.addWidget(self.folder, 1)
        folder_row.addWidget(self.folder_browse)

        # one: the file, and how big
        self.target = QLineEdit(str(target), self)
        self.target.setMinimumWidth(360)
        self.target_browse = QPushButton(
            translate("Dialog - Export Loops", "Browse..."), self
        )
        self.target_browse.clicked.connect(self.browse_target)

        target_row = QHBoxLayout()
        target_row.addWidget(self.target, 1)
        target_row.addWidget(self.target_browse)

        self.size = QComboBox(self)
        for value, title in (
            (
                OutputSize.LARGEST,
                translate("Dialog - Export Loops", "As the biggest of the videos"),
            ),
            (OutputSize.P1080, translate("Dialog - Export Loops", "1080p")),
            (OutputSize.P720, translate("Dialog - Export Loops", "720p")),
        ):
            self.size.addItem(title, value)
        self.size.setCurrentIndex(max(self.size.findData(size), 0))

        self.fade, self.order, self.quality = _common_editors(
            self, fade_s, order, quality
        )

        modes = QFormLayout()
        modes.addRow(translate("Dialog - Export Loops", "Export:"), self.each_button)
        modes.addRow("", self.one_button)

        self.each_panel = QWidget(self)
        each_form = QFormLayout(self.each_panel)
        each_form.setContentsMargins(0, 0, 0, 0)
        each_form.addRow(
            translate("Dialog - Export Loops", "Save:"), self.beside_button
        )
        each_form.addRow("", folder_row)

        self.one_panel = QWidget(self)
        one_form = QFormLayout(self.one_panel)
        one_form.setContentsMargins(0, 0, 0, 0)
        one_form.addRow(translate("Dialog - Export Loops", "Save as:"), target_row)
        one_form.addRow(translate("Dialog - Export Loops", "Size:"), self.size)

        common = QFormLayout()
        common.addRow(
            translate("Dialog - Export Loops", "Fade between loops:"), self.fade
        )
        common.addRow(translate("Dialog - Export Loops", "Order:"), self.order)
        common.addRow(translate("Dialog - Export Loops", "Quality:"), self.quality)

        note = translate(
            "Dialog - Export Loops", "Videos with loops: {VIDEOS}, loops: {LOOPS}."
        ).format(VIDEOS=video_count, LOOPS=loop_count)
        if left_out:
            note += " " + translate(
                "Dialog - Export Loops",
                "Left out, with no finished loop or not a file: {COUNT}.",
            ).format(COUNT=left_out)
        self.count_note = QLabel(note, self)
        self.count_note.setWordWrap(True)

        self.buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel, Qt.Horizontal, self
        )
        self.ok_button = self.buttons.button(QDialogButtonBox.Ok)
        self.ok_button.setText(translate("Dialog - Export Loops", "Export"))
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(modes)
        layout.addWidget(self.each_panel)
        layout.addWidget(self.one_panel)
        layout.addLayout(common)
        layout.addWidget(self.count_note)
        layout.addWidget(self.buttons)

        # once all of it is there
        self.each_button.toggled.connect(self._update)
        self.in_folder_button.toggled.connect(self._update)
        self.folder.textChanged.connect(self._update)
        self.target.textChanged.connect(self._update)

        self._update()

    @property
    def mode(self) -> AllMode:
        return AllMode.EACH if self.each_button.isChecked() else AllMode.ONE

    def _update(self, *_):
        is_each = self.mode == AllMode.EACH

        self.each_panel.setVisible(is_each)
        self.one_panel.setVisible(not is_each)

        is_in_folder = self.in_folder_button.isChecked()
        self.folder.setEnabled(is_in_folder)
        self.folder_browse.setEnabled(is_in_folder)

        if is_each:
            is_ok = not is_in_folder or bool(self.folder.text().strip())
        else:
            is_ok = bool(self.target.text().strip())

        self.ok_button.setEnabled(is_ok)

    def browse_folder(self):
        folder = QFileDialog.getExistingDirectory(
            self,
            translate("Dialog - Export Loops", "Export Loops of All Videos"),
            self.folder.text(),
        )
        if folder:
            self.folder.setText(folder)
            self.in_folder_button.setChecked(True)

    def browse_target(self):
        path, _ = QFileDialog.getSaveFileName(
            self,
            translate("Dialog - Export Loops", "Export Loops of All Videos"),
            self.target.text(),
            "{} (*.mp4)".format(translate("Dialog - Export Loops", "MP4 video")),
        )
        if path:
            self.target.setText(path)

    def options(self) -> ExportAllOptions:
        target = Path(self.target.text().strip())
        if target.suffix.lower() != ".mp4":
            target = target.with_name(target.name + ".mp4")

        folder = None
        if self.in_folder_button.isChecked():
            folder = Path(self.folder.text().strip())

        return ExportAllOptions(
            mode=self.mode,
            folder=folder,
            target=target,
            size=self.size.currentData(),
            fade_s=self.fade.value(),
            order=self.order.currentData(),
            quality=self.quality.currentData(),
        )

    @classmethod
    def ask(cls, parent, **kwargs) -> ExportAllOptions | None:
        dialog = cls(parent=parent, **kwargs)

        if not dialog.exec():
            return None

        return dialog.options()
