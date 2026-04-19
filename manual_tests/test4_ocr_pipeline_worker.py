"""Manual Test 4: OCR Pipeline Worker (end-to-end)

Component: OcrPipelineWorker (realtime/ocr_worker.py)

What to check:
  - OCR recognizes Japanese text from a screen region
  - Cache reports correct state
  - Cleanup via close() does not raise

Step 1: A red rectangle appears on screen — drag/resize it over Japanese text,
        then close the window.
Step 2: The script captures that region and runs OCR.

Requires a display with Japanese text visible (manga page, game, NHK News, etc.).
"""
from __future__ import annotations

import sys

# ---------------------------------------------------------------
# Step 1: Let the user pick the region visually
# ---------------------------------------------------------------

from PySide6.QtCore import Qt, QRect, QPoint
from PySide6.QtGui import QPainter, QColor, QPen
from PySide6.QtWidgets import QApplication, QWidget, QLabel


class RegionPicker(QWidget):
    """Full-screen transparent overlay — click and drag to select a region."""

    def __init__(self) -> None:
        super().__init__(None)
        self.setWindowFlags(
            Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.FramelessWindowHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.showFullScreen()
        self.setCursor(Qt.CursorShape.CrossCursor)

        self._origin: QPoint | None = None
        self._rect: QRect | None = None
        self.selected_rect: QRect | None = None

        hint = QLabel("Click and drag to select the region with Japanese text. Release to confirm.", self)
        hint.setStyleSheet(
            "color: white; background: rgba(0,0,0,180); padding: 8px; font-size: 14px;"
        )
        hint.move(20, 20)

    def mousePressEvent(self, event) -> None:
        self._origin = event.position().toPoint()
        self._rect = QRect(self._origin, self._origin)

    def mouseMoveEvent(self, event) -> None:
        if self._origin is not None:
            self._rect = QRect(self._origin, event.position().toPoint()).normalized()
            self.update()

    def mouseReleaseEvent(self, event) -> None:
        if self._rect is not None and self._rect.width() > 10 and self._rect.height() > 10:
            # Qt uses logical pixels, mss uses physical pixels.
            # Monitor origins are the same in both systems, but positions
            # WITHIN a monitor are scaled by device pixel ratio (DPR).
            # So: offset from monitor origin * DPR + monitor origin = mss coords.
            top_left = self.mapToGlobal(self._rect.topLeft())
            screen = self.screen()
            origin = screen.geometry().topLeft()
            dpr = screen.devicePixelRatio()
            offset_x = top_left.x() - origin.x()
            offset_y = top_left.y() - origin.y()
            w = self._rect.width()
            h = self._rect.height()
            self.selected_rect = QRect(
                origin.x() + int(offset_x * dpr),
                origin.y() + int(offset_y * dpr),
                int(w * dpr),
                int(h * dpr),
            )
            self.close()
        else:
            self._origin = None
            self._rect = None

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        # Dim the whole screen slightly
        painter.fillRect(self.rect(), QColor(0, 0, 0, 60))
        if self._rect is not None:
            # Clear the selected area so it shows the actual screen content
            painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Clear)
            painter.fillRect(self._rect, Qt.GlobalColor.transparent)
            # Draw a red border around the selection
            painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
            pen = QPen(QColor(255, 0, 0), 2)
            painter.setPen(pen)
            painter.drawRect(self._rect)
        painter.end()

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key.Key_Escape:
            self.selected_rect = None
            self.close()


picker_app = QApplication.instance() or QApplication(sys.argv)

print("=" * 50)
print("Test 4: OCR Pipeline Worker")
print("=" * 50)

# Debug: show coordinate systems from both sides
print("\n--- Qt screen info ---")
for i, screen in enumerate(picker_app.screens()):
    geo = screen.geometry()
    dpr = screen.devicePixelRatio()
    print(f"  Screen {i}: {screen.name()}  geo=({geo.x()},{geo.y()}) {geo.width()}x{geo.height()}  dpr={dpr}")

print("\n--- mss monitor info ---")
import mss
with mss.mss() as sct:
    for i, mon in enumerate(sct.monitors):
        print(f"  Monitor {i}: left={mon['left']} top={mon['top']} {mon['width']}x{mon['height']}")

print("\nA fullscreen overlay will appear.")
print("Click and drag to select the region containing Japanese text.")
print("Press Escape to cancel.\n")

picker = RegionPicker()
picker_app.exec()

if picker.selected_rect is None:
    print("No region selected — cancelled.")
    sys.exit(0)

ROI_X = picker.selected_rect.x()
ROI_Y = picker.selected_rect.y()
ROI_WIDTH = picker.selected_rect.width()
ROI_HEIGHT = picker.selected_rect.height()

# ---------------------------------------------------------------
# Step 2: Capture + OCR
# ---------------------------------------------------------------

# Choose OCR backend: "manga_ocr" (best quality) or "tesseract"
OCR_BACKEND = "manga-ocr"

print(f"Selected ROI: ({ROI_X}, {ROI_Y}) {ROI_WIDTH}x{ROI_HEIGHT}")
print(f"OCR backend:  {OCR_BACKEND}")

from jp_anki_builder.screen_capture import build_screen_capture
from jp_anki_builder.ocr import build_ocr_provider
from jp_anki_builder.realtime.ocr_worker import OcrPipelineWorker

try:
    cap = build_screen_capture("mss")
    print(f"Capture:      {type(cap).__name__}")
except Exception as exc:
    print(f"Screen capture failed: {exc}")
    sys.exit(1)

try:
    ocr = build_ocr_provider(OCR_BACKEND)
    print(f"OCR provider: {type(ocr).__name__}")
except Exception as exc:
    print(f"OCR provider failed: {exc}")
    cap.close()
    sys.exit(1)

worker = OcrPipelineWorker(cap, ocr)

# Debug: capture the region directly and save it so we can see what mss grabbed.
print("\nDebug: capturing region directly with mss...")
debug_frame = cap.grab_region(ROI_X, ROI_Y, ROI_WIDTH, ROI_HEIGHT)
if debug_frame is not None:
    from PIL import Image
    debug_path = "manual_tests/debug_capture.png"
    Image.fromarray(debug_frame, mode="RGB").save(debug_path)
    print(f"  Saved captured image to: {debug_path}")
    print(f"  Frame shape: {debug_frame.shape}")
    print("  >>> Open debug_capture.png to verify it matches your selection <<<")
else:
    print("  Capture returned None (unchanged)")

# Need a fresh capture for the worker since mss change detection will return None.
# Reinitialize the capture backend.
cap.close()
cap = build_screen_capture("mss")
worker = OcrPipelineWorker(cap, ocr)

print("\nRunning OCR on selected region...")
text = worker.process_region(ROI_X, ROI_Y, ROI_WIDTH, ROI_HEIGHT)
if text:
    print(f"  Result: {text!r}")
else:
    print("  Result: None (region unchanged or OCR returned empty)")

print(f"  Cache:  {worker.cache_info()}")

# Second call — should hit cache or return None (unchanged)
text2 = worker.process_region(ROI_X, ROI_Y, ROI_WIDTH, ROI_HEIGHT)
print(f"  Second: {text2!r} (expected: same text from cache, or None if unchanged)")

worker.close()
print("  close(): OK")

print("\nDone.")
