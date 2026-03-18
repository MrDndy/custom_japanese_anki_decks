"""Manual Test 6: RealtimeController — Live Pipeline

Component: RealtimeController (realtime/controller.py)

What to check:
  - Full capture → OCR → lookup → signal pipeline works end-to-end
  - Results appear when hovering over Japanese text on screen
  - DPI-aware coordinate mapping: captured region matches cursor position
    on both monitors (LG TV 2.0 DPR, ROG PG279Q 1.25 DPR)
  - Frame dropping: moving cursor quickly skips stale OCR results
  - Change detection: holding cursor still triggers cache hits, not repeated OCR
  - Thread lifecycle: start and stop are clean, no hangs
  - shutdown() releases capture resources without error

How to use:
  1. Open a window with Japanese text (manga reader, game, NHK News, etc.)
  2. Run this script: python manual_tests/test6_controller.py
  3. Hover your cursor over Japanese text — results print in the terminal
  4. Try hovering on each monitor to verify DPI mapping
  5. Hold cursor still — watch for "cache hit" messages (no repeated OCR)
  6. Move cursor quickly — watch for "dropping stale result" messages
  7. The script runs for 30 seconds then stops automatically
     (or press Ctrl+C to stop early)
  8. Check manual_tests/debug_frames/ for captured images to verify
     the ROI is capturing the correct screen region.
"""
from __future__ import annotations

import logging
import os
import sys
import time

from PIL import Image
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from jp_anki_builder.realtime.controller import RealtimeController

# Show debug logs so we can see cache hits, frame drops, etc.
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s.%(msecs)03d [%(name)s] %(message)s",
    datefmt="%H:%M:%S",
)

# Suppress extremely noisy httpcore/httpx logs (manga-ocr model checks)
for noisy in ("httpcore", "httpx", "urllib3", "huggingface_hub"):
    logging.getLogger(noisy).setLevel(logging.WARNING)

DURATION_SECONDS = 30
CAPTURE_BACKEND = "mss"  # "mss" (cross-platform) or "dxcam" (Windows, faster)
OCR_MODE = "manga-ocr"

app = QApplication.instance() or QApplication(sys.argv)

print("=" * 60)
print("Test 6: RealtimeController — Live Pipeline")
print("=" * 60)

# --- Show monitor info for DPI debugging ---

print("\n--- Monitor info ---")
for i, screen in enumerate(app.screens()):
    geo = screen.geometry()
    dpr = screen.devicePixelRatio()
    phys_w = int(geo.width() * dpr)
    phys_h = int(geo.height() * dpr)
    print(
        f"  Screen {i}: {screen.name()}  "
        f"logical=({geo.x()},{geo.y()}) {geo.width()}x{geo.height()}  "
        f"physical={phys_w}x{phys_h}  dpr={dpr}"
    )

# --- Create controller ---

print(f"\nCapture backend: {CAPTURE_BACKEND}")
print(f"OCR mode:        {OCR_MODE}")

ctrl = RealtimeController(
    capture_backend=CAPTURE_BACKEND,
    ocr_mode=OCR_MODE,
    roi_width=150,
    roi_height=80,
    poll_ms=50,
)

# --- Debug frame saving ---
# Wrap the capture backend to save every unique frame to disk so we can
# visually verify the ROI is targeting the correct screen region.

DEBUG_DIR = "manual_tests/debug_frames"
os.makedirs(DEBUG_DIR, exist_ok=True)
# Clean previous run
for f in os.listdir(DEBUG_DIR):
    if f.endswith(".png"):
        os.remove(os.path.join(DEBUG_DIR, f))

_frame_seq = 0
_real_grab = ctrl._ocr_worker._capture.grab_region


def _debug_grab(x, y, width, height):
    global _frame_seq
    frame = _real_grab(x, y, width, height)
    if frame is not None:
        _frame_seq += 1
        path = os.path.join(DEBUG_DIR, f"frame_{_frame_seq:04d}_roi_{x}_{y}_{width}x{height}.png")
        Image.fromarray(frame, mode="RGB").save(path)
        if _frame_seq <= 3:
            print(f"  [debug] Saved {path}  shape={frame.shape}")
        elif _frame_seq == 4:
            print(f"  [debug] (further frames saved silently to {DEBUG_DIR}/)")
    return frame


ctrl._ocr_worker._capture.grab_region = _debug_grab
print(f"\nDebug frames will be saved to: {DEBUG_DIR}/")

# --- Track results ---

result_count = 0
result_times: list[float] = []
last_result_time = 0.0
start_time = 0.0


def on_lookup_ready(response) -> None:
    global result_count, last_result_time
    result_count += 1
    now = time.perf_counter()
    elapsed = now - start_time

    words_summary = []
    for w in response.words:
        reading = f" ({w.reading})" if w.reading else ""
        jlpt = f" [{w.jlpt_level}]" if w.jlpt_level else ""
        meanings = f" — {'; '.join(w.meanings[:3])}" if w.meanings else ""
        words_summary.append(f"    {w.surface} → {w.dictionary_form}{reading}{jlpt}{meanings}")

    if response.words:
        print(f"\n[{elapsed:6.1f}s] Result #{result_count}  "
              f"({response.processing_time_ms:.0f}ms lookup)  "
              f"raw={response.raw_text!r}")
        for line in words_summary:
            print(line)
        result_times.append(response.processing_time_ms)
    else:
        print(f"[{elapsed:6.1f}s] Result #{result_count}: "
              f"(no words after filtering)  raw={response.raw_text!r}")

    last_result_time = now


def on_status_changed(status: str) -> None:
    elapsed = time.perf_counter() - start_time if start_time else 0
    print(f"[{elapsed:6.1f}s] Status: {status}")


ctrl.lookup_ready.connect(on_lookup_ready)
ctrl.status_changed.connect(on_status_changed)

# --- Start scanning ---

print(f"\nStarting scan... hover over Japanese text on screen.")
print(f"Running for {DURATION_SECONDS} seconds (Ctrl+C to stop early).\n")

start_time = time.perf_counter()
ctrl.start_scanning()
assert ctrl.scanning, "Controller should be scanning after start_scanning()"

# --- Auto-stop timer ---


def finish() -> None:
    elapsed = time.perf_counter() - start_time
    print(f"\n{'=' * 60}")
    print(f"Stopping after {elapsed:.1f}s...")

    t0 = time.perf_counter()
    stopped = ctrl.stop_scanning(timeout_ms=5000)
    stop_ms = (time.perf_counter() - t0) * 1000
    print(f"  stop_scanning(): {'OK' if stopped else 'TIMED OUT'}  ({stop_ms:.0f}ms)")
    assert stopped, "Thread did not stop within 5s — possible hang!"
    assert not ctrl.scanning, "Controller should not be scanning after stop"

    ctrl.shutdown()
    print("  shutdown():      OK")

    print(f"\n--- Summary ---")
    print(f"  Total results:   {result_count}")
    if result_times:
        avg_ms = sum(result_times) / len(result_times)
        max_ms = max(result_times)
        min_ms = min(result_times)
        print(f"  Lookup latency:  avg={avg_ms:.0f}ms  min={min_ms:.0f}ms  max={max_ms:.0f}ms")
        if avg_ms > 200:
            print("  WARNING: average latency exceeds 200ms target")
    else:
        print("  No results with words received — was Japanese text visible on screen?")

    print(f"  Debug frames:    {_frame_seq} saved to {DEBUG_DIR}/")
    if _frame_seq > 0:
        print(f"  >>> Open the PNG files in {DEBUG_DIR}/ to verify the ROI <<<")
        print(f"  >>> File names include ROI coordinates: frame_NNNN_roi_X_Y_WxH.png <<<")

    print(f"\nChecklist:")
    print(f"  [ ] Results appeared when hovering over Japanese text")
    print(f"  [ ] Captured region matched cursor position (not offset)")
    print(f"  [ ] Debug frames show the expected screen content under cursor")
    print(f"  [ ] Tested on multiple monitors with different DPR")
    print(f"  [ ] 'cache hit' log messages appeared when cursor was still")
    print(f"  [ ] 'dropping stale result' log messages appeared when moving fast")
    print(f"  [ ] stop_scanning() returned promptly, no hang")
    print(f"\nDone.")

    app.quit()


QTimer.singleShot(DURATION_SECONDS * 1000, finish)

try:
    sys.exit(app.exec())
except KeyboardInterrupt:
    finish()
