"""Floating session word list panel for the real-time overlay."""
from __future__ import annotations

import logging

from jp_anki_builder.realtime.session import SessionWord

logger = logging.getLogger(__name__)

_PYSIDE6_AVAILABLE = False

try:
    from PySide6.QtCore import Qt, Signal
    from PySide6.QtWidgets import (
        QApplication,
        QFrame,
        QHBoxLayout,
        QLabel,
        QLineEdit,
        QPushButton,
        QScrollArea,
        QSizePolicy,
        QVBoxLayout,
        QWidget,
    )

    _PYSIDE6_AVAILABLE = True

    def _button_style(bg: str, hover_bg: str) -> str:
        return (
            f"QPushButton {{"
            f"  color: #FFFFFF; font-size: 12px;"
            f"  background: {bg};"
            f"  border: none; border-radius: 5px;"
            f"  padding: 5px 12px;"
            f"}}"
            f"QPushButton:hover {{ background: {hover_bg}; }}"
        )

    class BufferPanel(QWidget):
        """Panel showing words added during the current session.

        When created without a parent (default), acts as a floating
        always-on-top window.  When created with a parent widget, it
        embeds inline without special window flags.
        """

        word_removed = Signal(int)    # index of removed word
        export_requested = Signal(str)  # deck name
        clear_requested = Signal()

        def __init__(self, parent: QWidget | None = None) -> None:
            super().__init__(parent)
            if parent is None:
                # Floating mode — standalone overlay window
                self.setWindowFlags(
                    Qt.WindowType.WindowStaysOnTopHint
                    | Qt.WindowType.FramelessWindowHint
                    | Qt.WindowType.Tool
                )
                self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
            self.setMinimumWidth(340)
            self._setup_ui()

        # ------------------------------------------------------------------
        # Public API
        # ------------------------------------------------------------------

        def update_words(self, words: list[SessionWord]) -> None:
            """Refresh the word list display."""
            # Clear existing rows
            while self._list_layout.count():
                item = self._list_layout.takeAt(0)
                widget = item.widget()
                if widget is not None:
                    widget.deleteLater()

            for idx, word in enumerate(words):
                self._add_word_row(idx, word)

            count = len(words)
            self._count_label.setText(f"{count} word{'s' if count != 1 else ''}")

        def show_export_success(self, deck_path: str) -> None:
            """Show confirmation after successful export."""
            self._status_label.setText(f"Exported: {deck_path}")
            self._status_label.setStyleSheet(
                "color: #88FF88; font-size: 11px; background: transparent;"
            )
            self._status_label.show()

        # ------------------------------------------------------------------
        # Private helpers
        # ------------------------------------------------------------------

        def _setup_ui(self) -> None:
            outer = QVBoxLayout(self)
            outer.setContentsMargins(0, 0, 0, 0)
            outer.setSpacing(0)

            # Outer frame provides dark semi-transparent background.
            frame = QFrame()
            frame.setStyleSheet(
                "QFrame {"
                "  background-color: rgba(24, 24, 28, 230);"
                "  border-radius: 10px;"
                "}"
            )
            outer.addWidget(frame)

            inner = QVBoxLayout(frame)
            inner.setContentsMargins(10, 10, 10, 10)
            inner.setSpacing(8)

            # Title bar
            title_row = QHBoxLayout()
            title_row.setSpacing(6)
            title_lbl = QLabel("Session Buffer")
            title_lbl.setStyleSheet(
                "color: #FFFFFF; font-size: 14px; font-weight: bold; background: transparent;"
            )
            title_row.addWidget(title_lbl)
            title_row.addStretch()
            self._count_label = QLabel("0 words")
            self._count_label.setStyleSheet(
                "color: #AAAAAA; font-size: 11px; background: transparent;"
            )
            title_row.addWidget(self._count_label)
            inner.addLayout(title_row)

            # Separator
            sep = QFrame()
            sep.setFrameShape(QFrame.Shape.HLine)
            sep.setStyleSheet("color: rgba(255,255,255,40);")
            inner.addWidget(sep)

            # Scrollable word list
            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            scroll.setMaximumHeight(300)
            scroll.setStyleSheet(
                "QScrollArea { border: none; background: transparent; }"
                "QScrollBar:vertical {"
                "  background: rgba(255,255,255,20); width: 6px; border-radius: 3px;"
                "}"
                "QScrollBar::handle:vertical {"
                "  background: rgba(255,255,255,80); border-radius: 3px;"
                "}"
                "QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }"
            )

            list_container = QWidget()
            list_container.setStyleSheet("background: transparent;")
            self._list_layout = QVBoxLayout(list_container)
            self._list_layout.setContentsMargins(0, 0, 0, 0)
            self._list_layout.setSpacing(4)
            self._list_layout.addStretch()

            scroll.setWidget(list_container)
            inner.addWidget(scroll)

            # Deck name input
            name_row = QHBoxLayout()
            name_row.setSpacing(6)
            name_lbl = QLabel("Deck:")
            name_lbl.setStyleSheet(
                "color: #AAAAAA; font-size: 12px; background: transparent;"
            )
            name_row.addWidget(name_lbl)
            self._deck_name_input = QLineEdit()
            self._deck_name_input.setPlaceholderText("session")
            self._deck_name_input.setText("session")
            self._deck_name_input.setStyleSheet(
                "QLineEdit {"
                "  color: #FFFFFF; font-size: 12px;"
                "  background: rgba(255,255,255,20);"
                "  border: 1px solid rgba(255,255,255,60);"
                "  border-radius: 4px; padding: 3px 6px;"
                "}"
            )
            name_row.addWidget(self._deck_name_input)
            inner.addLayout(name_row)

            # Status label (hidden until export succeeds)
            self._status_label = QLabel("")
            self._status_label.setStyleSheet(
                "color: #AAAAAA; font-size: 11px; background: transparent;"
            )
            self._status_label.setWordWrap(True)
            self._status_label.hide()
            inner.addWidget(self._status_label)

            # Action buttons
            btn_row = QHBoxLayout()
            btn_row.setSpacing(6)

            self._export_btn = QPushButton("Export")
            self._export_btn.setStyleSheet(_button_style("#2266CC", "#1A4A99"))
            self._export_btn.clicked.connect(self._on_export_clicked)
            btn_row.addWidget(self._export_btn)

            self._clear_btn = QPushButton("Clear")
            self._clear_btn.setStyleSheet(_button_style("#555555", "#333333"))
            self._clear_btn.clicked.connect(self.clear_requested)
            btn_row.addWidget(self._clear_btn)

            inner.addLayout(btn_row)

        def _add_word_row(self, idx: int, word: SessionWord) -> None:
            """Insert a single word row before the stretch."""
            row_widget = QFrame()
            row_widget.setStyleSheet(
                "QFrame {"
                "  background-color: rgba(255,255,255,12);"
                "  border-radius: 5px;"
                "}"
            )
            row_layout = QHBoxLayout(row_widget)
            row_layout.setContentsMargins(8, 6, 6, 6)
            row_layout.setSpacing(6)

            # Left: word info (two lines)
            info_col = QVBoxLayout()
            info_col.setSpacing(2)

            # Line 1: surface + reading on same line
            top_row = QHBoxLayout()
            top_row.setSpacing(6)
            surface_lbl = QLabel(word.dictionary_form)
            surface_lbl.setStyleSheet(
                "color: #FFFFFF; font-size: 15px; font-weight: bold; background: transparent;"
            )
            top_row.addWidget(surface_lbl)

            if word.reading:
                reading_lbl = QLabel(word.reading)
                reading_lbl.setStyleSheet(
                    "color: #AAAAAA; font-size: 11px; background: transparent;"
                )
                top_row.addWidget(reading_lbl, alignment=Qt.AlignmentFlag.AlignBaseline)

            # JLPT badge on same line
            if word.jlpt_level:
                badge = QLabel(word.jlpt_level)
                badge.setStyleSheet(
                    "color: #FFD700; font-size: 10px; font-weight: bold;"
                    " background: rgba(90, 70, 0, 200);"
                    " border-radius: 3px; padding: 1px 4px;"
                )
                top_row.addWidget(badge, alignment=Qt.AlignmentFlag.AlignVCenter)

            top_row.addStretch()
            info_col.addLayout(top_row)

            # Line 2: meaning
            meaning_text = word.meanings[0] if word.meanings else ""
            if meaning_text:
                meaning_lbl = QLabel(meaning_text)
                meaning_lbl.setStyleSheet(
                    "color: #CCCCCC; font-size: 11px; background: transparent;"
                )
                meaning_lbl.setWordWrap(True)
                info_col.addWidget(meaning_lbl)

            row_layout.addLayout(info_col, stretch=1)

            # Remove button
            remove_btn = QPushButton("\u2715")
            remove_btn.setFixedSize(22, 22)
            remove_btn.setStyleSheet(
                "QPushButton {"
                "  color: #888888; font-size: 11px;"
                "  background: transparent; border: none;"
                "}"
                "QPushButton:hover { color: #FF6666; }"
            )
            # Capture idx in default argument to avoid late-binding closure.
            remove_btn.clicked.connect(lambda checked=False, i=idx: self.word_removed.emit(i))
            row_layout.addWidget(remove_btn, alignment=Qt.AlignmentFlag.AlignTop)

            # Insert before the trailing stretch item.
            insert_pos = max(0, self._list_layout.count() - 1)
            self._list_layout.insertWidget(insert_pos, row_widget)

        def _on_export_clicked(self) -> None:
            deck_name = self._deck_name_input.text().strip() or "session"
            self._status_label.hide()
            self.export_requested.emit(deck_name)

except ImportError:
    # PySide6 not installed — provide a stub so the module is always importable.
    class BufferPanel:  # type: ignore[no-redef]
        """Stub used when PySide6 is not installed."""

        def __init__(self) -> None:
            raise ImportError(
                "The buffer panel requires PySide6. "
                "Install with: pip install PySide6"
            )

        def update_words(self, words) -> None:  # noqa: ARG002
            raise ImportError("The buffer panel requires PySide6.")

        def show_export_success(self, deck_path: str) -> None:  # noqa: ARG002
            raise ImportError("The buffer panel requires PySide6.")
