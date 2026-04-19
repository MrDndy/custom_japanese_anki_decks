"""Entry point for launching the GUI application."""
from __future__ import annotations

import sys


def launch_gui(data_dir: str = "data") -> int:
    """Create QApplication and MainWindow, then run the event loop."""
    from PySide6.QtWidgets import QApplication

    from jp_anki_builder.gui.main_window import MainWindow

    app = QApplication.instance() or QApplication(sys.argv)
    window = MainWindow(data_dir=data_dir)
    window.show()
    return app.exec()
