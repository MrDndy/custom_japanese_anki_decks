"""Manual Test 1: Overlay Widget — Visual Appearance + Click-Through

Component: OverlayWidget (realtime/overlay.py)

What to check:
  - Dark semi-transparent cards appear over whatever is behind them
  - Two cards visible: "食べる" with N4 badge, "友達" with N5 badge
  - Readings and meanings are readable
  - Click-through: clicks pass through to the window beneath
  - No taskbar entry for the popup
  - Popup stays on top of other windows

Auto-closes after 15 seconds, or press Ctrl+C in the terminal.
"""
from __future__ import annotations

import sys

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from jp_anki_builder.lookup_service import LookupResult
from jp_anki_builder.realtime.overlay import OverlayWidget

app = QApplication(sys.argv)

widget = OverlayWidget()

results = [
    LookupResult(
        surface="食べた",
        dictionary_form="食べる",
        reading="たべる",
        meanings=["to eat", "to consume", "to live on"],
        part_of_speech="動詞",
        confidence=0.99,
        jlpt_level="N4",
        is_in_vocab_db=False,
    ),
    LookupResult(
        surface="友達",
        dictionary_form="友達",
        reading="ともだち",
        meanings=["friend", "companion"],
        part_of_speech="名詞",
        confidence=0.99,
        jlpt_level="N5",
        is_in_vocab_db=True,
    ),
]

screen = app.primaryScreen().geometry()
cx, cy = screen.center().x(), screen.center().y()
print(f"Showing overlay at ({cx}, {cy}) — center of screen")
print("Check: transparency, click-through, no taskbar entry, stays on top")
print("Auto-closes in 15 seconds...")
widget.show_results(results, cx, cy)

QTimer.singleShot(15000, app.quit)
sys.exit(app.exec())
