from __future__ import annotations

import hashlib
import logging
from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    import numpy as np

logger = logging.getLogger(__name__)


@runtime_checkable
class ScreenCapture(Protocol):
    def grab_region(self, x: int, y: int, width: int, height: int) -> "np.ndarray | None":
        """Capture a screen region. Returns RGB numpy array or None if unchanged."""
        ...


class DXcamCapture:
    """Windows screen capture using DXcam (DXGI Desktop Duplication API).

    ~240 FPS capable, ~4ms latency. Returns None natively when the captured
    region has not changed since the last call (built-in change detection).
    """

    def __init__(self) -> None:
        self._camera = None

    def _get_camera(self):
        if self._camera is not None:
            return self._camera
        try:
            import dxcam
        except ImportError as exc:
            raise RuntimeError(
                "DXcam is not installed. Install with: pip install dxcam"
            ) from exc
        self._camera = dxcam.create(output_color="RGB")
        return self._camera

    def grab_region(self, x: int, y: int, width: int, height: int) -> "np.ndarray | None":
        """Capture region. Returns RGB numpy array or None if content unchanged."""
        camera = self._get_camera()
        region = (x, y, x + width, y + height)
        return camera.grab(region=region)


class MssCapture:
    """Cross-platform screen capture using mss.

    Works on Windows, macOS, and Linux. Change detection is emulated via an
    MD5 hash of the captured frame — returns None when the content is identical
    to the previous capture.
    """

    def __init__(self) -> None:
        self._sct = None
        self._last_hash: str | None = None

    def _get_sct(self):
        if self._sct is not None:
            return self._sct
        try:
            import mss
        except ImportError as exc:
            raise RuntimeError(
                "mss is not installed. Install with: pip install mss"
            ) from exc
        self._sct = mss.mss()
        return self._sct

    def grab_region(self, x: int, y: int, width: int, height: int) -> "np.ndarray | None":
        """Capture region. Returns RGB numpy array or None if content unchanged."""
        import numpy as np

        sct = self._get_sct()
        monitor = {"top": y, "left": x, "width": width, "height": height}
        shot = sct.grab(monitor)
        # mss returns BGRA (4 channels); select R,G,B from indices 2,1,0.
        frame = np.array(shot, dtype=np.uint8)[:, :, 2::-1]

        frame_hash = hashlib.md5(frame.tobytes(), usedforsecurity=False).hexdigest()
        if frame_hash == self._last_hash:
            return None
        self._last_hash = frame_hash
        return frame


def build_screen_capture(backend: str = "dxcam") -> ScreenCapture:
    """Factory: returns the requested capture backend, falling back to mss if needed."""
    if backend == "dxcam":
        try:
            capture = DXcamCapture()
            capture._get_camera()  # verify dxcam is usable now
            return capture
        except Exception as exc:
            logger.warning("DXcam unavailable (%s), falling back to mss", exc)
            return MssCapture()
    if backend == "mss":
        return MssCapture()
    raise ValueError(
        f"Unsupported screen capture backend: {backend!r}. Use: dxcam or mss."
    )
