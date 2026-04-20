"""Entry point for launching the GUI application."""
from __future__ import annotations

import logging
import sys

logger = logging.getLogger(__name__)

try:
    from PySide6.QtWidgets import QApplication

    def launch_gui(data_dir: str = "data") -> int:
        """Create QApplication and MainWindow, then run the event loop."""
        from jp_anki_builder.gui.main_window import MainWindow

        app = QApplication.instance() or QApplication(sys.argv)
        window = MainWindow(data_dir=data_dir)
        window.show()
        return app.exec()

except ImportError:
    def launch_gui(data_dir: str = "data") -> int:  # type: ignore[no-redef]
        raise ImportError(
            "The GUI requires PySide6. Install with: pip install PySide6"
        )
