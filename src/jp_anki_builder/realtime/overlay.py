from __future__ import annotations

import logging
import sys

from jp_anki_builder.lookup_service import LookupResult

logger = logging.getLogger(__name__)

_PYSIDE6_AVAILABLE = False

_CURSOR_OFFSET_X = 20
_CURSOR_OFFSET_Y = 20
_MAX_POPUP_WIDTH = 360

try:
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import (
        QApplication,
        QFrame,
        QHBoxLayout,
        QLabel,
        QVBoxLayout,
        QWidget,
    )

    _PYSIDE6_AVAILABLE = True

    class OverlayWidget(QWidget):
        """Transparent, always-on-top, click-through popup showing word definitions.

        Must be created in the main (Qt event loop) thread.
        """

        def __init__(self) -> None:
            super().__init__(None)
            self.setWindowFlags(
                Qt.WindowType.WindowStaysOnTopHint
                | Qt.WindowType.FramelessWindowHint
                | Qt.WindowType.Tool
            )
            self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
            self._setup_ui()

        # ------------------------------------------------------------------
        # Public API
        # ------------------------------------------------------------------

        def show_results(
            self,
            results: list[LookupResult],
            cursor_x: int,
            cursor_y: int,
        ) -> None:
            """Position the popup near *cursor_x/y* and display *results*."""
            self._clear_entries()
            if not results:
                self.hide()
                return
            for result in results:
                self._add_word_card(result)
            self.adjustSize()
            self._position_near_cursor(cursor_x, cursor_y)
            self.show()

        def hide_results(self) -> None:
            """Hide the popup."""
            self.hide()

        # ------------------------------------------------------------------
        # Qt overrides
        # ------------------------------------------------------------------

        def showEvent(self, event) -> None:  # noqa: N802
            super().showEvent(event)
            _apply_click_through(self)

        # ------------------------------------------------------------------
        # Private helpers
        # ------------------------------------------------------------------

        def _setup_ui(self) -> None:
            self._layout = QVBoxLayout(self)
            self._layout.setContentsMargins(8, 8, 8, 8)
            self._layout.setSpacing(6)
            self.setMaximumWidth(_MAX_POPUP_WIDTH)
            self.setStyleSheet("background: transparent;")

        def _clear_entries(self) -> None:
            while self._layout.count():
                item = self._layout.takeAt(0)
                widget = item.widget()
                if widget is not None:
                    widget.deleteLater()

        def _add_word_card(self, result: LookupResult) -> None:
            card = QFrame()
            card.setStyleSheet(
                "QFrame {"
                "  background-color: rgba(18, 18, 18, 220);"
                "  border-radius: 8px;"
                "}"
            )
            card_layout = QVBoxLayout(card)
            card_layout.setContentsMargins(10, 8, 10, 8)
            card_layout.setSpacing(3)

            # Row 1: word (large) + JLPT badge
            header = QHBoxLayout()
            header.setSpacing(6)

            word_lbl = QLabel(result.dictionary_form)
            word_lbl.setStyleSheet(
                "color: #FFFFFF; font-size: 22px; font-weight: bold; background: transparent;"
            )
            header.addWidget(word_lbl)

            if result.jlpt_level:
                badge = QLabel(result.jlpt_level)
                badge.setStyleSheet(
                    "color: #FFD700; font-size: 11px; font-weight: bold;"
                    " background: rgba(90, 70, 0, 200);"
                    " border-radius: 4px; padding: 1px 5px;"
                )
                header.addWidget(badge, alignment=Qt.AlignmentFlag.AlignVCenter)

            header.addStretch()
            card_layout.addLayout(header)

            # Row 2: reading
            if result.reading:
                reading_lbl = QLabel(result.reading)
                reading_lbl.setStyleSheet(
                    "color: #AAAAAA; font-size: 13px; background: transparent;"
                )
                card_layout.addWidget(reading_lbl)

            # Rows 3+: meanings (top 3)
            for meaning in result.meanings[:3]:
                m_lbl = QLabel(f"• {meaning}")
                m_lbl.setStyleSheet(
                    "color: #DDDDDD; font-size: 12px; background: transparent;"
                )
                m_lbl.setWordWrap(True)
                card_layout.addWidget(m_lbl)

            self._layout.addWidget(card)

        def _position_near_cursor(self, cursor_x: int, cursor_y: int) -> None:
            """Move the widget near *cursor_x/y*, clamping to screen bounds."""
            from PySide6.QtCore import QPoint

            x = cursor_x + _CURSOR_OFFSET_X
            y = cursor_y + _CURSOR_OFFSET_Y
            w = self.width()
            h = self.height()

            # Use the screen the cursor is actually on (multi-monitor safe).
            screen = QApplication.screenAt(QPoint(cursor_x, cursor_y))
            if screen is None:
                screen = QApplication.primaryScreen()
            if screen is not None:
                geom = screen.geometry()
                # Flip left/up when popup would overflow right or bottom edge.
                if x + w > geom.right():
                    x = cursor_x - w - _CURSOR_OFFSET_X
                if y + h > geom.bottom():
                    y = cursor_y - h - _CURSOR_OFFSET_Y
                # Clamp to screen rectangle.
                x = max(geom.left(), min(x, geom.right() - w))
                y = max(geom.top(), min(y, geom.bottom() - h))

            self.move(x, y)

except ImportError:
    # PySide6 not installed — provide a stub so the module is always importable.
    class OverlayWidget:  # type: ignore[no-redef]
        """Stub used when PySide6 is not installed."""

        def __init__(self) -> None:
            raise ImportError(
                "The real-time overlay requires PySide6. "
                "Install with: pip install PySide6"
            )

        def show_results(self, results, cursor_x: int, cursor_y: int) -> None:  # noqa: ARG002
            raise ImportError("The real-time overlay requires PySide6.")

        def hide_results(self) -> None:
            raise ImportError("The real-time overlay requires PySide6.")


def _apply_click_through(widget) -> None:
    """Set WS_EX_LAYERED | WS_EX_TRANSPARENT on *widget* so mouse events pass through.

    No-op on non-Windows platforms.
    """
    if sys.platform != "win32":
        return
    try:
        import ctypes

        _GWL_EXSTYLE = -20
        _WS_EX_LAYERED = 0x00080000
        _WS_EX_TRANSPARENT = 0x00000020
        _SWP_NOMOVE = 0x0002
        _SWP_NOSIZE = 0x0001
        _SWP_NOZORDER = 0x0004
        _SWP_FRAMECHANGED = 0x0020

        hwnd = int(widget.winId())
        ex_style = ctypes.windll.user32.GetWindowLongW(hwnd, _GWL_EXSTYLE)
        ctypes.windll.user32.SetWindowLongW(
            hwnd, _GWL_EXSTYLE, ex_style | _WS_EX_LAYERED | _WS_EX_TRANSPARENT
        )
        # Flush the style change so Windows applies it immediately.
        ctypes.windll.user32.SetWindowPos(
            hwnd, None, 0, 0, 0, 0,
            _SWP_NOMOVE | _SWP_NOSIZE | _SWP_NOZORDER | _SWP_FRAMECHANGED,
        )
        logger.debug("click-through set for hwnd=%d", hwnd)
    except Exception as exc:
        logger.warning("Failed to set Win32 click-through: %s", exc)
