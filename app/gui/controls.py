"""Selection controls that do not change accidentally while scrolling a form."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QComboBox


class ClickComboBox(QComboBox):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFocusPolicy(Qt.StrongFocus)

    def wheelEvent(self, event):
        if self.view().isVisible():
            super().wheelEvent(event)
        else:
            event.ignore()
