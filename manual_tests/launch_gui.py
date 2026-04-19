"""Quick launcher for manual GUI testing (before Task 4.07 adds the CLI command)."""
from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication

from jp_anki_builder.gui.main_window import MainWindow

app = QApplication.instance() or QApplication(sys.argv)
w = MainWindow(data_dir="data")
w.show()
sys.exit(app.exec())
