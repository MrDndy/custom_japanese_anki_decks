"""Qt-threaded controller for the real-time capture → OCR → lookup pipeline."""
from __future__ import annotations

import logging
from typing import Callable

logger = logging.getLogger(__name__)

_PYSIDE6_AVAILABLE = False

# Cursor must move more than this many logical pixels between the start of a
# capture and the end of OCR for the result to be treated as stale.
_STALE_CURSOR_THRESHOLD_PX = 16


def _map_logical_to_physical(
    cursor_x: int,
    cursor_y: int,
    roi_width: int,
    roi_height: int,
    origin_x: int,
    origin_y: int,
    dpr: float,
    screen_width: int = 0,
    screen_height: int = 0,
) -> tuple[int, int, int, int]:
    """Convert a logical-pixel cursor position to a physical-pixel mss ROI.

    The ROI is centered on the cursor.  Coordinates are clamped to >= 0
    and, when *screen_width*/*screen_height* are provided (> 0), the far
    edge is clamped to not exceed the physical screen bounds.

    Args:
        cursor_x / cursor_y: Qt logical global cursor position.
        roi_width / roi_height: desired capture size in logical pixels.
        origin_x / origin_y: top-left corner of the monitor in logical pixels
            (same value in both Qt logical and physical coordinate systems).
        dpr: device pixel ratio of the monitor (e.g. 1.25 at 125 % scaling).
        screen_width / screen_height: physical screen size in pixels.
            Pass 0 to skip upper-bound clamping.

    Returns:
        (x, y, width, height) in physical screen pixels suitable for mss.
    """
    phys_cursor_x = origin_x + int((cursor_x - origin_x) * dpr)
    phys_cursor_y = origin_y + int((cursor_y - origin_y) * dpr)
    phys_w = int(roi_width * dpr)
    phys_h = int(roi_height * dpr)
    x = max(0, phys_cursor_x - phys_w // 2)
    y = max(0, phys_cursor_y - phys_h // 2)
    if screen_width > 0 and x + phys_w > screen_width:
        x = max(0, screen_width - phys_w)
    if screen_height > 0 and y + phys_h > screen_height:
        y = max(0, screen_height - phys_h)
    return x, y, phys_w, phys_h


try:
    from PySide6.QtCore import QObject, QThread, QTimer, Signal
    from PySide6.QtCore import Qt as _Qt
    from PySide6.QtGui import QCursor
    from PySide6.QtWidgets import QApplication

    _PYSIDE6_AVAILABLE = True

    # Alias so signal connections can specify type explicitly.
    # Defined here (before class bodies) so it's in scope when start_scanning runs.
    Qt_ConnectionType = _Qt.ConnectionType

    class _ScanThread(QThread):
        """Worker thread: capture → OCR → lookup → emit signal.

        *lookup_service_factory* is injectable for testing; defaults to
        constructing a real LookupService inside the thread.

        Threading notes:
        - All Qt GUI calls (QCursor.pos, QApplication.screenAt) are made on the
          main thread via a QTimer in RealtimeController._sample_cursor().
        - The cursor snapshot is written by the main thread and read by this
          thread.  Python's GIL makes tuple-reference assignment atomic in
          CPython, so no explicit lock is needed.
        - Interruption uses QThread.requestInterruption() / isInterruptionRequested(),
          the Qt-idiomatic thread-safe stop mechanism.
        """

        lookup_ready = Signal(object)   # emits TextLookupResponse
        status_changed = Signal(str)    # "scanning" | "idle" | "error"

        def __init__(
            self,
            data_dir: str,
            ocr_worker,
            roi_width: int,
            roi_height: int,
            poll_ms: int,
            lookup_service_factory: Callable | None = None,
            parent: QObject | None = None,
        ) -> None:
            super().__init__(parent)
            self._data_dir = data_dir
            self._ocr_worker = ocr_worker
            self._roi_width = roi_width
            self._roi_height = roi_height
            self._poll_ms = poll_ms
            self._lookup_service_factory = lookup_service_factory
            # Cursor snapshot: (cx, cy, origin_x, origin_y, dpr, screen_w, screen_h)
            # Set by the main thread via update_cursor_snapshot(); read here.
            self._cursor_snapshot: tuple[int, int, int, int, float, int, int] | None = None

        def update_cursor_snapshot(
            self,
            cx: int,
            cy: int,
            origin_x: int,
            origin_y: int,
            dpr: float,
            screen_width: int = 0,
            screen_height: int = 0,
        ) -> None:
            """Push a new cursor position+DPR snapshot from the main thread.

            The tuple assignment is atomic under CPython's GIL, so no lock is
            required for the simple producer-consumer pattern here.
            """
            self._cursor_snapshot = (cx, cy, origin_x, origin_y, dpr, screen_width, screen_height)

        def run(self) -> None:  # noqa: C901
            from jp_anki_builder.lookup_service import LookupService

            factory = self._lookup_service_factory or (
                lambda dd: LookupService(data_dir=dd)
            )
            lookup_service = factory(self._data_dir)
            self.status_changed.emit("scanning")

            try:
                while not self.isInterruptionRequested():
                    snapshot = self._cursor_snapshot
                    if snapshot is None:
                        # Timer hasn't fired yet; wait and retry.
                        self.msleep(self._poll_ms)
                        continue

                    cx, cy, origin_x, origin_y, dpr, screen_w, screen_h = snapshot
                    x, y, w, h = _map_logical_to_physical(
                        cx, cy, self._roi_width, self._roi_height,
                        origin_x, origin_y, dpr, screen_w, screen_h,
                    )
                    text = self._ocr_worker.process_region(x, y, w, h)
                    if text:
                        # Frame-drop check: if the cursor moved significantly
                        # while OCR was running, the result is for stale content.
                        # Re-capture immediately rather than showing wrong text.
                        new_snapshot = self._cursor_snapshot
                        if new_snapshot is not None:
                            ncx, ncy = new_snapshot[0], new_snapshot[1]
                            if (
                                abs(ncx - cx) > _STALE_CURSOR_THRESHOLD_PX
                                or abs(ncy - cy) > _STALE_CURSOR_THRESHOLD_PX
                            ):
                                logger.debug(
                                    "cursor moved during OCR (%d,%d)→(%d,%d), "
                                    "dropping stale result",
                                    cx, cy, ncx, ncy,
                                )
                                continue  # skip lookup, loop to re-capture
                        try:
                            response = lookup_service.lookup(text)
                            self.lookup_ready.emit(response)
                        except Exception as exc:
                            logger.warning("lookup error: %s", exc)
                    self.msleep(self._poll_ms)
            except Exception as exc:
                logger.error("scan loop error: %s", exc)
                self.status_changed.emit("error")
            finally:
                try:
                    lookup_service.close()
                except Exception:
                    pass
                self.status_changed.emit("idle")

    class RealtimeController(QObject):
        """Orchestrates the capture → OCR → lookup → display pipeline.

        Runs capture + OCR + lookup in a worker thread and emits results to the
        main thread via Qt signals.  The main thread connects ``lookup_ready``
        to the overlay widget.

        Threading notes:
        - This object lives on the main (Qt event-loop) thread.
        - A QTimer fires every poll_ms on the main thread to sample
          QCursor.pos() and per-monitor DPR.  The snapshot is pushed to
          _ScanThread via update_cursor_snapshot() — keeping all Qt GUI calls
          on the main thread.
        - ``_ScanThread`` creates its own ``LookupService`` inside ``run()``
          so that Sudachi is initialised and used on a single consistent thread.
        - Qt signals cross the thread boundary safely via the queued connection
          mechanism.
        """

        lookup_ready = Signal(object)  # emits TextLookupResponse
        status_changed = Signal(str)   # "scanning" | "idle" | "error"

        def __init__(
            self,
            data_dir: str = "data",
            ocr_mode: str = "manga-ocr",
            capture_backend: str = "dxcam",
            roi_width: int = 80,
            roi_height: int = 80,
            poll_ms: int = 50,
            min_edge_density: float = 0.01,
        ) -> None:
            super().__init__()
            from jp_anki_builder.ocr import build_ocr_provider
            from jp_anki_builder.realtime.ocr_worker import OcrPipelineWorker
            from jp_anki_builder.screen_capture import build_screen_capture

            self._data_dir = data_dir
            self._roi_width = roi_width
            self._roi_height = roi_height
            self._poll_ms = poll_ms

            capture = build_screen_capture(capture_backend)
            ocr_provider = build_ocr_provider(ocr_mode)
            self._ocr_worker = OcrPipelineWorker(capture, ocr_provider, min_edge_density=min_edge_density)
            self._thread: _ScanThread | None = None
            self._cursor_timer: QTimer | None = None

        @property
        def scanning(self) -> bool:
            return self._thread is not None and self._thread.isRunning()

        def start_scanning(
            self,
            lookup_service_factory: Callable | None = None,
        ) -> None:
            """Begin continuous capture + OCR around the cursor position."""
            if self.scanning:
                return
            self._thread = _ScanThread(
                data_dir=self._data_dir,
                ocr_worker=self._ocr_worker,
                roi_width=self._roi_width,
                roi_height=self._roi_height,
                poll_ms=self._poll_ms,
                lookup_service_factory=lookup_service_factory,
            )
            self._thread.lookup_ready.connect(
                self.lookup_ready, type=Qt_ConnectionType.QueuedConnection
            )
            self._thread.status_changed.connect(
                self.status_changed, type=Qt_ConnectionType.QueuedConnection
            )
            # Cursor-sampling timer: fires on the main thread so Qt GUI calls
            # (QCursor.pos, QApplication.screenAt) never run in the worker.
            self._cursor_timer = QTimer(self)
            self._cursor_timer.setInterval(self._poll_ms)
            self._cursor_timer.timeout.connect(self._sample_cursor)
            self._cursor_timer.start()
            self._thread.start()
            logger.debug("scan thread started")

        def _sample_cursor(self) -> None:
            """Sample cursor position and per-monitor DPR on the main thread.

            Called by _cursor_timer every poll_ms.  Pushes the snapshot into
            the worker thread so it never needs to call Qt GUI APIs itself.
            """
            if self._thread is None:
                return
            from PySide6.QtCore import QPoint

            pos = QCursor.pos()
            cx, cy = pos.x(), pos.y()
            screen = QApplication.screenAt(QPoint(cx, cy))
            if screen is None:
                screen = QApplication.primaryScreen()
            if screen is not None:
                origin = screen.geometry().topLeft()
                geom = screen.geometry()
                dpr = screen.devicePixelRatio()
                screen_w = int(geom.width() * dpr)
                screen_h = int(geom.height() * dpr)
                self._thread.update_cursor_snapshot(
                    cx, cy, origin.x(), origin.y(), dpr, screen_w, screen_h,
                )
            else:
                # No screen info available — use 1:1 fallback, no upper clamp
                self._thread.update_cursor_snapshot(cx, cy, 0, 0, 1.0, 0, 0)

        def stop_scanning(self, timeout_ms: int = 5000) -> bool:
            """Stop the scan loop and wait for the worker thread to finish.

            Returns True if the thread stopped within *timeout_ms*, False if
            it timed out (thread may still be running).
            """
            if self._cursor_timer is not None:
                self._cursor_timer.stop()
                self._cursor_timer.deleteLater()
                self._cursor_timer = None
            if self._thread is None or not self._thread.isRunning():
                return True
            self._thread.requestInterruption()
            stopped = self._thread.wait(timeout_ms)
            if stopped:
                self._thread.lookup_ready.disconnect(self.lookup_ready)
                self._thread.status_changed.disconnect(self.status_changed)
                logger.debug("scan thread stopped")
            else:
                logger.warning("scan thread did not stop within %d ms", timeout_ms)
            return stopped

        def shutdown(self) -> None:
            """Stop scanning and release capture resources.

            Unlike stop_scanning(), this waits indefinitely for the worker
            thread to finish before closing the capture device.  The indefinite
            wait guarantees that no thread is mid-process_region() when close()
            runs, eliminating the data-race that a timed wait cannot prevent.
            """
            if self._cursor_timer is not None:
                self._cursor_timer.stop()
                self._cursor_timer.deleteLater()
                self._cursor_timer = None
            if self._thread is not None and self._thread.isRunning():
                self._thread.requestInterruption()
                self._thread.wait()  # indefinite — guarantees thread is done
            try:
                self._ocr_worker.close()
            except Exception:
                pass

except ImportError:
    class RealtimeController:  # type: ignore[no-redef]
        """Stub used when PySide6 is not installed."""

        def __init__(self, *args, **kwargs) -> None:
            raise ImportError(
                "RealtimeController requires PySide6. "
                "Install with: pip install PySide6"
            )
