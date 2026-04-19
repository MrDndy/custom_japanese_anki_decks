"""Manual Test 3: Screen Capture Abstraction

Component: ScreenCapture / MssCapture / DXcamCapture (screen_capture.py)

What to check:
  - First grab returns an RGB numpy array with expected shape
  - Second grab of the same region returns None (unchanged content)
  - Cleanup via close() does not raise

Runs in the terminal — no GUI needed.
"""
from __future__ import annotations

from jp_anki_builder.screen_capture import build_screen_capture

print("=" * 50)
print("Test 3: Screen Capture Abstraction")
print("=" * 50)

for backend in ("mss", "dxcam"):
    print(f"\n--- Backend: {backend} ---")
    try:
        cap = build_screen_capture(backend)
    except Exception as exc:
        print(f"  Skipped ({exc})")
        continue

    backend_name = type(cap).__name__
    print(f"  Using: {backend_name}")

    frame = cap.grab_region(100, 100, 400, 200)
    if frame is not None:
        print(f"  First grab:  shape={frame.shape}, dtype={frame.dtype}")
        assert frame.shape == (200, 400, 3), f"Unexpected shape: {frame.shape}"
        assert str(frame.dtype) == "uint8", f"Unexpected dtype: {frame.dtype}"
        print("  First grab:  OK")
    else:
        print("  First grab:  None (no change detected — may happen with DXcam)")

    frame2 = cap.grab_region(100, 100, 400, 200)
    if frame2 is None:
        print("  Second grab: None (unchanged) — OK")
    else:
        print(f"  Second grab: got frame (content may have changed on screen)")

    cap.close()
    print("  close():     OK")

print("\nDone.")
