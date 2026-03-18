"""Top-level overlay application.

Wires together RealtimeController, OverlayWidget, BufferPanel, SessionBuffer,
and HotkeyManager into a single runnable Qt application.

Usage::

    from jp_anki_builder.realtime.app import OverlayApp
    import sys
    sys.exit(OverlayApp(data_dir="data").run())
"""
from __future__ import annotations

import logging
import signal
import sys

from jp_anki_builder.realtime.hotkeys import (
    DEFAULT_HOTKEY_ADD_WORD,
    DEFAULT_HOTKEY_EXPORT,
    DEFAULT_HOTKEY_SCAN,
    HotkeyManager,
)
from jp_anki_builder.realtime.session import SessionBuffer

logger = logging.getLogger(__name__)

_PYSIDE6_AVAILABLE = False

try:
    from PySide6.QtCore import QObject, QTimer, Signal
    from PySide6.QtWidgets import QApplication

    _PYSIDE6_AVAILABLE = True

    class _HotkeyBridge(QObject):
        """Marshals pynput hotkey callbacks from the listener thread to the Qt
        main thread via queued signal connections.

        All Qt-touching code (start_scanning, stop_scanning, widget updates)
        runs on the main thread; pynput callbacks only call .emit() here,
        which is thread-safe for cross-thread queued connections.
        """

        scan_start = Signal()
        scan_stop = Signal()
        add_word = Signal()
        export_session = Signal()

    class OverlayApp:
        """Main application class that assembles all real-time components.

        Parameters
        ----------
        data_dir:
            Root data directory (same as for the batch pipeline).
        ocr_mode:
            OCR backend to use: ``"manga-ocr"`` (default), ``"tesseract"``,
            or ``"sidecar"``.
        capture_backend:
            Screen capture backend: ``"dxcam"`` (Windows, fastest) or
            ``"mss"`` (cross-platform fallback).
        hotkey_scan:
            Hold-to-scan hotkey string, e.g. ``"ctrl+shift"``.
        hotkey_add_word:
            Add-word hotkey string, e.g. ``"ctrl+shift+a"``.
        hotkey_export:
            Export-session hotkey string, e.g. ``"ctrl+shift+e"``.
        """

        def __init__(
            self,
            data_dir: str = "data",
            ocr_mode: str = "manga-ocr",
            capture_backend: str = "dxcam",
            hotkey_scan: str = DEFAULT_HOTKEY_SCAN,
            hotkey_add_word: str = DEFAULT_HOTKEY_ADD_WORD,
            hotkey_export: str = DEFAULT_HOTKEY_EXPORT,
            anki_client=None,
        ) -> None:
            self._qt_app = QApplication.instance() or QApplication(sys.argv)
            self._hotkey_scan = hotkey_scan

            # Core components
            from jp_anki_builder.realtime.buffer_panel import BufferPanel
            from jp_anki_builder.realtime.controller import RealtimeController
            from jp_anki_builder.realtime.overlay import OverlayWidget

            self._controller = RealtimeController(
                data_dir=data_dir,
                ocr_mode=ocr_mode,
                capture_backend=capture_backend,
            )
            self._overlay = OverlayWidget()
            self._buffer_panel = BufferPanel()
            self._session = SessionBuffer(data_dir=data_dir, anki_client=anki_client)
            self._hotkeys = HotkeyManager()
            self._bridge = _HotkeyBridge()

            # State
            self._last_response = None  # last TextLookupResponse received

            # Wire everything together
            self._connect_signals(hotkey_scan, hotkey_add_word, hotkey_export)

        # ------------------------------------------------------------------
        # Public API
        # ------------------------------------------------------------------

        def run(self) -> int:
            """Start the application event loop. Returns exit code."""
            # Allow Ctrl+C in the terminal to cleanly quit.
            signal.signal(signal.SIGINT, self._handle_sigint)
            # QTimer wakes the Python interpreter periodically so SIGINT is
            # actually delivered on Windows (where the event loop blocks it).
            self._sigint_timer = QTimer()
            self._sigint_timer.setInterval(200)
            self._sigint_timer.timeout.connect(lambda: None)
            self._sigint_timer.start()

            try:
                self._hotkeys.start()
            except RuntimeError as exc:
                logger.warning("hotkey manager unavailable: %s", exc)

            self._buffer_panel.show()
            logger.info("overlay app started — hold %s to scan", self._hotkey_scan)

            exit_code = self._qt_app.exec()
            self.shutdown()
            return exit_code

        def shutdown(self) -> None:
            """Clean shutdown: stop scanning, stop hotkeys, close overlay."""
            try:
                self._controller.shutdown()
            except Exception as exc:
                logger.warning("controller shutdown error: %s", exc)

            try:
                self._hotkeys.stop()
            except Exception as exc:
                logger.warning("hotkey stop error: %s", exc)

            try:
                self._overlay.hide()
                self._buffer_panel.hide()
            except Exception as exc:
                logger.debug("widget hide error during shutdown: %s", exc)

        # ------------------------------------------------------------------
        # Signal wiring
        # ------------------------------------------------------------------

        def _connect_signals(
            self,
            hotkey_scan: str,
            hotkey_add_word: str,
            hotkey_export: str,
        ) -> None:
            # --- Hotkey bridge: pynput thread → main thread ---
            self._hotkeys.register(
                hotkey_scan,
                callback=lambda: self._bridge.scan_start.emit(),
                on_release=lambda: self._bridge.scan_stop.emit(),
            )
            self._hotkeys.register(
                hotkey_add_word,
                callback=lambda: self._bridge.add_word.emit(),
            )
            self._hotkeys.register(
                hotkey_export,
                callback=lambda: self._bridge.export_session.emit(),
            )

            # --- Bridge signals → main-thread slots ---
            self._bridge.scan_start.connect(self._on_scan_start)
            self._bridge.scan_stop.connect(self._on_scan_stop)
            self._bridge.add_word.connect(self._on_add_word)
            self._bridge.export_session.connect(self._on_export_session)

            # --- Controller → overlay ---
            self._controller.lookup_ready.connect(self._on_lookup_ready)
            self._controller.status_changed.connect(self._on_status_changed)

            # --- BufferPanel interactions ---
            self._buffer_panel.word_removed.connect(self._on_word_removed)
            self._buffer_panel.export_requested.connect(self._on_export_requested)
            self._buffer_panel.clear_requested.connect(self._on_clear_requested)

        # ------------------------------------------------------------------
        # Slot implementations (always on main thread)
        # ------------------------------------------------------------------

        def _on_scan_start(self) -> None:
            """Hotkey pressed: begin scanning."""
            if not self._controller.scanning:
                self._controller.start_scanning()
                logger.debug("scan started via hotkey")

        def _on_scan_stop(self) -> None:
            """Hotkey released: stop scanning and hide overlay."""
            if self._controller.scanning:
                self._controller.stop_scanning()
            self._overlay.hide_results()
            self._last_response = None
            logger.debug("scan stopped via hotkey")

        def _on_lookup_ready(self, response) -> None:
            """New OCR+lookup result: update overlay near current cursor."""
            self._last_response = response
            if response.words:
                from PySide6.QtGui import QCursor

                pos = QCursor.pos()
                self._overlay.show_results(response.words, pos.x(), pos.y())
            else:
                self._overlay.hide_results()

        def _on_status_changed(self, status: str) -> None:
            logger.debug("controller status: %s", status)
            if status in ("idle", "error"):
                self._overlay.hide_results()

        def _on_add_word(self) -> None:
            """Add-word hotkey pressed: add current top word to session buffer."""
            if self._last_response is None or not self._last_response.words:
                logger.debug("add_word: no current lookup result")
                return
            top_result = self._last_response.words[0]
            added = self._session.add_word(top_result, self._last_response.raw_text)
            if added:
                logger.info("added word: %s", top_result.dictionary_form)
                self._buffer_panel.update_words(self._session.get_words())
            else:
                logger.debug("add_word: duplicate, skipped")

        def _on_export_session(self) -> None:
            """Export hotkey pressed: export buffer to Anki deck."""
            self._on_export_requested("session")

        def _on_word_removed(self, index: int) -> None:
            self._session.remove_word(index)
            self._buffer_panel.update_words(self._session.get_words())

        def _on_export_requested(self, deck_name: str) -> None:
            if len(self._session) == 0:
                logger.info("export requested but buffer is empty")
                return
            try:
                deck_path = self._session.export_deck(deck_name)
                self._buffer_panel.show_export_success(str(deck_path))
                logger.info("exported deck: %s", deck_path)
            except Exception as exc:
                logger.error("export failed: %s", exc)

        def _on_clear_requested(self) -> None:
            self._session.clear()
            self._buffer_panel.update_words([])

        def _handle_sigint(self, signum, frame) -> None:
            logger.info("SIGINT received, shutting down")
            self._qt_app.quit()

except ImportError:
    class OverlayApp:  # type: ignore[no-redef]
        """Stub used when PySide6 is not installed."""

        def __init__(self, *args, **kwargs) -> None:
            raise ImportError(
                "OverlayApp requires PySide6. "
                "Install with: pip install PySide6"
            )

        def run(self) -> int:
            raise ImportError("OverlayApp requires PySide6.")

        def shutdown(self) -> None:
            raise ImportError("OverlayApp requires PySide6.")
