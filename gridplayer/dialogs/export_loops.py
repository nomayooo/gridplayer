"""What exporting a video's loops is to make: where to, how long each fades
into the next, in what order, and how good (see utils.loop_export)."""

from dataclasses import dataclass
from pathlib import Path

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
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
    QVBoxLayout,
)

from gridplayer.utils.loop_export import ExportQuality, LoopOrder
from gridplayer.utils.qt import translate

# the longest fade asked for, in seconds
MAX_FADE_S = 5.0


@dataclass(frozen=True)
class ExportOptions:
    target: Path
    fade_s: float
    order: LoopOrder
    quality: ExportQuality


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

        self.fade = QDoubleSpinBox(self)
        self.fade.setRange(0.0, MAX_FADE_S)
        self.fade.setSingleStep(0.25)
        self.fade.setDecimals(2)
        self.fade.setSuffix(" s")
        self.fade.setValue(fade_s)
        self.fade.setSpecialValueText(translate("Dialog - Export Loops", "No fade"))

        self.order = QComboBox(self)
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
            self.order.addItem(title, value)
        self.order.setCurrentIndex(max(self.order.findData(order), 0))

        self.quality = QComboBox(self)
        for value, title in (
            (ExportQuality.HIGH, translate("Dialog - Export Loops", "High")),
            (ExportQuality.MEDIUM, translate("Dialog - Export Loops", "Medium")),
            (ExportQuality.SMALL, translate("Dialog - Export Loops", "Small file")),
        ):
            self.quality.addItem(title, value)
        self.quality.setCurrentIndex(max(self.quality.findData(quality), 0))

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
