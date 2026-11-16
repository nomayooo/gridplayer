"""A name typed in place, over where it is shown, rather than in a dialog:
a bare box laid over the name, Enter or a click away keeping what is
typed, Escape leaving it as it was.

A popup window of its own, as the overlay a name is shown on takes no keys:
it takes them while it is open, and closes on a click anywhere else."""

from PyQt5.QtCore import QRect, Qt, pyqtSignal
from PyQt5.QtWidgets import QLineEdit


class InlineNameEditor(QLineEdit):
    # what was typed, once done; None for leaving it as it was
    finished = pyqtSignal(object)

    def __init__(self, text: str, placeholder: str = "", parent=None):
        super().__init__(text, parent)

        self.setWindowFlags(Qt.Popup | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_DeleteOnClose)
        self.setPlaceholderText(placeholder)
        self.setFrame(False)
        self.selectAll()

        self._is_done = False

    def open_over(self, rect: QRect) -> None:
        """Shown over this, on the screen, typed into at once."""

        self.setGeometry(rect)
        self.show()
        self.activateWindow()
        self.setFocus(Qt.PopupFocusReason)

    def keyPressEvent(self, event):
        if event.key() in {Qt.Key_Return, Qt.Key_Enter}:
            self._finish(self.text())
            self.close()
            return

        if event.key() == Qt.Key_Escape:
            self._finish(None)
            self.close()
            return

        super().keyPressEvent(event)

    def closeEvent(self, event):
        # a click away closes a popup: what is typed kept, as Enter does
        self._finish(self.text())
        super().closeEvent(event)

    def _finish(self, text):
        if self._is_done:
            return

        self._is_done = True
        self.finished.emit(text)
