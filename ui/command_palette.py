from __future__ import annotations

from typing import Callable, List, Tuple

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QDialog, QLineEdit, QListWidget, QListWidgetItem, QVBoxLayout


class CommandPaletteDialog(QDialog):
    def __init__(self, commands: List[Tuple[str, Callable]], parent=None):
        super().__init__(parent)
        self.setWindowTitle("Command Palette")
        self.setModal(True)
        self.resize(560, 380)
        self.commands = commands
        self.filtered = list(commands)

        lay = QVBoxLayout(self)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Type a command...")
        self.search.textChanged.connect(self._apply_filter)
        lay.addWidget(self.search)

        self.listing = QListWidget()
        self.listing.itemDoubleClicked.connect(self._run_selected)
        lay.addWidget(self.listing)
        self._apply_filter("")

    def _apply_filter(self, raw: str):
        q = str(raw or "").strip().lower()
        self.listing.clear()
        if not q:
            self.filtered = list(self.commands)
        else:
            self.filtered = [c for c in self.commands if q in c[0].lower()]
        for name, _ in self.filtered:
            self.listing.addItem(QListWidgetItem(name))
        if self.listing.count():
            self.listing.setCurrentRow(0)

    def _run_selected(self):
        row = self.listing.currentRow()
        if row < 0 or row >= len(self.filtered):
            return
        _, fn = self.filtered[row]
        try:
            fn()
        finally:
            self.accept()

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self._run_selected()
            return
        super().keyPressEvent(event)

