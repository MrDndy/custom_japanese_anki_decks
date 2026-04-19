"""Manual Test 2: Overlay Positioning — Screen Edge Clamping

Component: OverlayWidget._position_near_cursor (realtime/overlay.py)

What to check:
  - Popup appears ABOVE and to the LEFT of the bottom-right corner
  - Popup does not extend off-screen
  - All text is fully visible

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
cx, cy = screen.right() - 10, screen.bottom() - 10
print(f"Showing overlay at bottom-right corner ({cx}, {cy})")
print("Check: popup should flip above/left and stay fully on-screen")
print("Auto-closes in 15 seconds...")
widget.show_results(results, cx, cy)

QTimer.singleShot(15000, app.quit)
sys.exit(app.exec())
