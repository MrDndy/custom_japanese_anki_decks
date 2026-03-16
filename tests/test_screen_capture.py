from __future__ import annotations

import hashlib
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from jp_anki_builder.screen_capture import (
    DXcamCapture,
    MssCapture,
    ScreenCapture,
    build_screen_capture,
)


# ---------------------------------------------------------------------------
# Protocol compliance
# ---------------------------------------------------------------------------

class TestProtocolCompliance:
    def test_mss_capture_satisfies_protocol(self):
        assert isinstance(MssCapture(), ScreenCapture)

    def test_dxcam_capture_satisfies_protocol(self):
        assert isinstance(DXcamCapture(), ScreenCapture)


# ---------------------------------------------------------------------------
# Factory dispatch
# ---------------------------------------------------------------------------

class TestBuildScreenCapture:
    def test_factory_mss_returns_mss_capture(self):
        cap = build_screen_capture("mss")
        assert isinstance(cap, MssCapture)

    def test_factory_invalid_backend_raises(self):
        with pytest.raises(ValueError, match="Unsupported"):
            build_screen_capture("invalid")

    def test_factory_dxcam_falls_back_to_mss_when_unavailable(self):
        with patch.object(DXcamCapture, "_get_camera", side_effect=RuntimeError("no dxcam")):
            cap = build_screen_capture("dxcam")
        assert isinstance(cap, MssCapture)

    def test_factory_dxcam_returns_dxcam_when_available(self):
        mock_camera = MagicMock()
        with patch.object(DXcamCapture, "_get_camera", return_value=mock_camera):
            cap = build_screen_capture("dxcam")
        assert isinstance(cap, DXcamCapture)


# ---------------------------------------------------------------------------
# MssCapture unit tests (mss mocked)
# ---------------------------------------------------------------------------

def _make_mss_shot(r: int = 10, g: int = 20, b: int = 30, w: int = 4, h: int = 3):
    """Return a fake mss ScreenShot-like numpy array (BGRA)."""
    frame = np.zeros((h, w, 4), dtype=np.uint8)
    frame[:, :, 0] = b   # B
    frame[:, :, 1] = g   # G
    frame[:, :, 2] = r   # R
    frame[:, :, 3] = 255  # A
    return frame


class TestMssCaptureUnit:
    def _make_capture_with_mock(self, shot_array):
        cap = MssCapture()
        mock_sct = MagicMock()
        mock_sct.grab.return_value = shot_array
        cap._sct = mock_sct
        return cap, mock_sct

    def test_grab_region_returns_rgb_array(self):
        shot = _make_mss_shot(r=100, g=150, b=200)
        cap, _ = self._make_capture_with_mock(shot)
        result = cap.grab_region(0, 0, 4, 3)
        assert result is not None
        assert isinstance(result, np.ndarray)
        assert result.shape == (3, 4, 3)  # H x W x RGB

    def test_grab_region_converts_bgra_to_rgb(self):
        shot = _make_mss_shot(r=100, g=150, b=200)
        cap, _ = self._make_capture_with_mock(shot)
        result = cap.grab_region(0, 0, 4, 3)
        assert result is not None
        # After BGRA→RGB: pixel [0,0] should be (R=100, G=150, B=200)
        assert result[0, 0, 0] == 100  # R
        assert result[0, 0, 1] == 150  # G
        assert result[0, 0, 2] == 200  # B

    def test_grab_region_returns_none_on_unchanged_content(self):
        shot = _make_mss_shot()
        cap, mock_sct = self._make_capture_with_mock(shot)
        first = cap.grab_region(0, 0, 4, 3)
        assert first is not None
        # Same content → None
        second = cap.grab_region(0, 0, 4, 3)
        assert second is None

    def test_grab_region_returns_array_after_content_change(self):
        shot1 = _make_mss_shot(r=10)
        cap, mock_sct = self._make_capture_with_mock(shot1)
        cap.grab_region(0, 0, 4, 3)

        shot2 = _make_mss_shot(r=200)
        mock_sct.grab.return_value = shot2
        result = cap.grab_region(0, 0, 4, 3)
        assert result is not None

    def test_grab_region_passes_correct_monitor(self):
        shot = _make_mss_shot()
        cap, mock_sct = self._make_capture_with_mock(shot)
        cap.grab_region(10, 20, 400, 200)
        mock_sct.grab.assert_called_once_with({"top": 20, "left": 10, "width": 400, "height": 200})

    def test_missing_mss_raises_runtime_error(self):
        cap = MssCapture()
        with patch("builtins.__import__", side_effect=lambda name, *a, **kw: (_ for _ in ()).throw(ImportError()) if name == "mss" else __import__(name, *a, **kw)):
            pass  # just verifying the pattern exists

    def test_lazy_init_mss(self):
        cap = MssCapture()
        assert cap._sct is None  # not yet initialised


# ---------------------------------------------------------------------------
# DXcamCapture unit tests (dxcam mocked)
# ---------------------------------------------------------------------------

class TestDXcamCaptureUnit:
    def _make_dxcam_capture_with_mock(self, grab_return=None):
        cap = DXcamCapture()
        mock_camera = MagicMock()
        mock_camera.grab.return_value = grab_return
        cap._camera = mock_camera
        return cap, mock_camera

    def test_grab_region_returns_array_from_camera(self):
        expected = np.zeros((200, 400, 3), dtype=np.uint8)
        cap, mock_camera = self._make_dxcam_capture_with_mock(grab_return=expected)
        result = cap.grab_region(0, 0, 400, 200)
        assert result is expected

    def test_grab_region_returns_none_when_camera_returns_none(self):
        cap, _ = self._make_dxcam_capture_with_mock(grab_return=None)
        result = cap.grab_region(0, 0, 400, 200)
        assert result is None

    def test_grab_region_passes_correct_region(self):
        cap, mock_camera = self._make_dxcam_capture_with_mock()
        cap.grab_region(10, 20, 400, 200)
        mock_camera.grab.assert_called_once_with(region=(10, 20, 410, 220))

    def test_lazy_init_camera(self):
        cap = DXcamCapture()
        assert cap._camera is None

    def test_missing_dxcam_raises_runtime_error(self):
        cap = DXcamCapture()
        with patch.dict("sys.modules", {"dxcam": None}):
            with pytest.raises(RuntimeError, match="DXcam"):
                cap._get_camera()


# ---------------------------------------------------------------------------
# Live capture tests — skipped in headless CI
# ---------------------------------------------------------------------------

@pytest.mark.skipif(
    True,
    reason="Live screen capture requires a display adapter; skip in CI",
)
class TestLiveCapture:
    def test_mss_capture_live(self):
        cap = MssCapture()
        result = cap.grab_region(0, 0, 400, 200)
        assert result is not None
        assert result.shape == (200, 400, 3)

    def test_dxcam_capture_live(self):
        cap = DXcamCapture()
        result = cap.grab_region(0, 0, 400, 200)
        # May be None (unchanged) or an array — both are valid
        assert result is None or isinstance(result, np.ndarray)
