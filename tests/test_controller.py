from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from jp_anki_builder.realtime.controller import (
    RealtimeController,
    _PYSIDE6_AVAILABLE,
    _map_logical_to_physical,
)


# ---------------------------------------------------------------------------
# Pure-function tests: DPI coordinate mapping (no Qt required)
# ---------------------------------------------------------------------------

class TestMapLogicalToPhysical:
    """Tests for _map_logical_to_physical — no PySide6 required."""

    def test_dpr_1_identity_mapping(self):
        x, y, w, h = _map_logical_to_physical(
            cursor_x=500, cursor_y=400,
            roi_width=400, roi_height=200,
            origin_x=0, origin_y=0,
            dpr=1.0,
        )
        assert w == 400
        assert h == 200
        # ROI centered on cursor: x = 500 - 200 = 300
        assert x == 300
        assert y == 300  # 400 - 100

    def test_dpr_2_doubles_dimensions(self):
        x, y, w, h = _map_logical_to_physical(
            cursor_x=200, cursor_y=100,
            roi_width=400, roi_height=200,
            origin_x=0, origin_y=0,
            dpr=2.0,
        )
        assert w == 800
        assert h == 400

    def test_dpr_2_scales_cursor_position(self):
        x, y, w, h = _map_logical_to_physical(
            cursor_x=200, cursor_y=100,
            roi_width=400, roi_height=200,
            origin_x=0, origin_y=0,
            dpr=2.0,
        )
        # Physical cursor: (400, 200); ROI center there; top-left = (400-400, 200-200)
        assert x == 0
        assert y == 0

    def test_dpr_1_25_fractional_scaling(self):
        x, y, w, h = _map_logical_to_physical(
            cursor_x=1000, cursor_y=500,
            roi_width=400, roi_height=200,
            origin_x=0, origin_y=0,
            dpr=1.25,
        )
        assert w == 500   # int(400 * 1.25)
        assert h == 250   # int(200 * 1.25)

    def test_non_zero_monitor_origin(self):
        """Second monitor at logical (1920, 0) with DPR 1.25."""
        x, y, w, h = _map_logical_to_physical(
            cursor_x=1920 + 100, cursor_y=50,
            roi_width=400, roi_height=200,
            origin_x=1920, origin_y=0,
            dpr=1.25,
        )
        # Offset within monitor: (100, 50) logical → (125, 62) physical
        phys_cursor_x = 1920 + int(100 * 1.25)   # = 2045
        phys_cursor_y = 0 + int(50 * 1.25)        # = 62
        phys_w = int(400 * 1.25)                   # = 500
        phys_h = int(200 * 1.25)                   # = 250
        assert x == max(0, phys_cursor_x - phys_w // 2)
        assert y == max(0, phys_cursor_y - phys_h // 2)
        assert w == phys_w
        assert h == phys_h

    def test_clamps_to_non_negative_x(self):
        x, y, w, h = _map_logical_to_physical(
            cursor_x=10, cursor_y=10,
            roi_width=400, roi_height=200,
            origin_x=0, origin_y=0,
            dpr=1.0,
        )
        assert x >= 0
        assert y >= 0

    def test_dpr_1_roi_centered_on_cursor(self):
        cx, cy = 640, 360
        x, y, w, h = _map_logical_to_physical(
            cursor_x=cx, cursor_y=cy,
            roi_width=400, roi_height=200,
            origin_x=0, origin_y=0,
            dpr=1.0,
        )
        # ROI center should be at cursor
        assert x + w // 2 == cx
        assert y + h // 2 == cy


# ---------------------------------------------------------------------------
# Module-level tests (no Qt required)
# ---------------------------------------------------------------------------

class TestModuleImport:
    def test_module_importable(self):
        import jp_anki_builder.realtime.controller  # noqa: F401

    def test_pyside6_available_flag_is_bool(self):
        assert isinstance(_PYSIDE6_AVAILABLE, bool)

    @pytest.mark.skipif(_PYSIDE6_AVAILABLE, reason="Only when PySide6 absent")
    def test_stub_raises_import_error(self):
        with pytest.raises(ImportError, match="PySide6"):
            RealtimeController()


# ---------------------------------------------------------------------------
# Qt lifecycle tests — skipped when PySide6 is not installed
# ---------------------------------------------------------------------------

@pytest.mark.skipif(not _PYSIDE6_AVAILABLE, reason="PySide6 not installed")
class TestControllerLifecycle:
    @pytest.fixture(autouse=True)
    def qt_app(self):
        from PySide6.QtWidgets import QApplication
        app = QApplication.instance() or QApplication([])
        yield app

    def _make_controller(self):
        """Controller with mocked capture and OCR so no real hardware is needed."""
        from jp_anki_builder.realtime.controller import RealtimeController

        ctrl = RealtimeController.__new__(RealtimeController)
        from PySide6.QtCore import QObject
        QObject.__init__(ctrl)

        from jp_anki_builder.realtime.ocr_worker import OcrPipelineWorker

        mock_capture = MagicMock()
        mock_capture.grab_region.return_value = None  # always "unchanged"
        mock_ocr = MagicMock()
        mock_ocr.extract_text.return_value = ""

        ctrl._data_dir = "data"
        ctrl._roi_width = 400
        ctrl._roi_height = 200
        ctrl._poll_ms = 1  # fast for tests
        ctrl._ocr_worker = OcrPipelineWorker(mock_capture, mock_ocr)
        ctrl._thread = None
        ctrl._cursor_timer = None
        return ctrl

    def _mock_lookup_factory(self):
        """LookupService factory that returns a fast mock."""
        mock_svc = MagicMock()
        mock_svc.lookup.return_value = MagicMock(words=[])
        mock_svc.close.return_value = None
        return lambda _data_dir: mock_svc

    def test_scanning_false_before_start(self):
        ctrl = self._make_controller()
        assert ctrl.scanning is False

    def test_start_sets_scanning_true(self):
        ctrl = self._make_controller()
        ctrl.start_scanning(lookup_service_factory=self._mock_lookup_factory())
        assert ctrl.scanning is True
        ctrl.stop_scanning(timeout_ms=2000)

    def test_stop_scanning_stops_thread(self):
        ctrl = self._make_controller()
        ctrl.start_scanning(lookup_service_factory=self._mock_lookup_factory())
        stopped = ctrl.stop_scanning(timeout_ms=2000)
        assert stopped, "Thread did not stop within 2 s"
        assert ctrl.scanning is False

    def test_double_start_is_idempotent(self):
        ctrl = self._make_controller()
        factory = self._mock_lookup_factory()
        ctrl.start_scanning(lookup_service_factory=factory)
        thread_id = id(ctrl._thread)
        ctrl.start_scanning(lookup_service_factory=factory)
        assert id(ctrl._thread) == thread_id  # same thread, not a second one
        ctrl.stop_scanning(timeout_ms=2000)

    def test_stop_when_not_running_returns_true(self):
        ctrl = self._make_controller()
        result = ctrl.stop_scanning(timeout_ms=500)
        assert result is True

    def test_shutdown_stops_thread(self):
        ctrl = self._make_controller()
        ctrl.start_scanning(lookup_service_factory=self._mock_lookup_factory())
        ctrl.shutdown()
        assert ctrl.scanning is False


