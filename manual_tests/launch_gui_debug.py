"""Launch GUI with debug logging to diagnose overlay positioning."""
from __future__ import annotations

import logging
import sys

logging.basicConfig(level=logging.DEBUG, format="%(name)s: %(message)s")

from PySide6.QtWidgets import QApplication

from jp_anki_builder.gui.main_window import MainWindow

app = QApplication.instance() or QApplication(sys.argv)
w = MainWindow(data_dir="data")
w.show()
sys.exit(app.exec())
