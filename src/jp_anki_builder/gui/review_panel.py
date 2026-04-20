"""Interactive word review panel for batch scan results."""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)

_PYSIDE6_AVAILABLE = False

# Confidence tier thresholds
_CONF_HIGH = 0.90   # dict_lookup
_CONF_MID = 0.70    # deinflection / partial match

# JLPT levels considered "common" for Approve N3+
_COMMON_JLPT_LEVELS = {"N3", "N4", "N5"}

# Row background colours (dark-theme friendly, semi-transparent tints)
_COLOR_HIGH = "rgba(30, 90, 50, 160)"    # green
_COLOR_MID = "rgba(90, 75, 15, 160)"     # amber
_COLOR_LOW = "rgba(90, 25, 20, 160)"     # red


@dataclass
class _CandidateRow:
    """Internal model for one candidate word in the review table."""

    lemma: str
    surface: str
    reading: str
    meaning: str
    confidence: float
    confidence_reason: str
    jlpt_level: str          # e.g. "N3" or ""
    flags: list[str]         # "OOV", "SFX", "low-confidence"
    approved: bool = True


def _load_scan_data(scan_path: Path) -> tuple[list[str], dict[str, dict]]:
    """Return (candidates, confidence_meta) from scan.json."""
    payload = json.loads(scan_path.read_text(encoding="utf-8-sig"))
    candidates: list[str] = payload.get("candidates", [])

    # Build lemma → best {confidence, reason, surface} from all normalized_candidates
    meta: dict[str, dict] = {}
    for record in payload.get("records", []):
        for nc in record.get("normalized_candidates", []):
            lemma = nc.get("lemma", "")
            if not lemma:
                continue
            conf = float(nc.get("confidence", 0.0))
            existing = meta.get(lemma)
            if existing is None or conf > existing["confidence"]:
                meta[lemma] = {
                    "confidence": conf,
                    "reason": nc.get("reason", ""),
                    "surface": nc.get("surface", lemma),
                }
    return candidates, meta


def _load_known_words(known_path: Path) -> set[str]:
    if not known_path.exists():
        return set()
    return {
        line.strip()
        for line in known_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    }


def _load_seen_words(seen_path: Path) -> set[str]:
    if not seen_path.exists():
        return set()
    payload = json.loads(seen_path.read_text(encoding="utf-8-sig"))
    return set(payload.get("seen_words", []))


def _append_known_words(known_path: Path, words: set[str]) -> None:
    existing = _load_known_words(known_path)
    merged = sorted(existing | words)
    known_path.parent.mkdir(parents=True, exist_ok=True)
    known_path.write_text("\n".join(merged) + "\n", encoding="utf-8")


def _confidence_tier(row: _CandidateRow) -> str:
    """Return 'high', 'mid', or 'low' for colour-coding."""
    if "OOV" in row.flags or row.confidence_reason == "surface_fallback":
        return "low"
    if row.confidence >= _CONF_HIGH and row.confidence_reason in ("dict_lookup", "normalized"):
        return "high"
    if row.confidence >= _CONF_MID:
        return "mid"
    return "low"


try:
    from PySide6.QtCore import QThread, Qt, Signal
    from PySide6.QtGui import QColor
    from PySide6.QtWidgets import (
        QAbstractItemView,
        QApplication,
        QFrame,
        QHBoxLayout,
        QLabel,
        QLineEdit,
        QPushButton,
        QSizePolicy,
        QTableWidget,
        QTableWidgetItem,
        QVBoxLayout,
        QWidget,
    )

    _PYSIDE6_AVAILABLE = True

    # -----------------------------------------------------------------------
    # Background worker for candidate enrichment
    # -----------------------------------------------------------------------

    class _CandidateEnrichWorker(QThread):
        """Builds dictionary/JLPT lookups and enriches candidates off the main thread."""

        finished = Signal(list)  # list[_CandidateRow]

        def __init__(
            self,
            candidates: list[str],
            conf_meta: dict[str, dict],
            data_dir: str,
            known_words: set[str],
            seen_words: set[str],
        ) -> None:
            super().__init__()
            self._candidates = candidates
            self._conf_meta = conf_meta
            self._data_dir = data_dir
            self._known_words = known_words
            self._seen_words = seen_words

        def run(self) -> None:
            from jp_anki_builder.dictionary import build_offline_dictionary
            from jp_anki_builder.filtering import is_sfx_token
            from jp_anki_builder.jlpt import build_jlpt_lookup

            offline_dict = build_offline_dictionary(self._data_dir)
            jlpt = build_jlpt_lookup(self._data_dir)

            rows: list[_CandidateRow] = []
            for lemma in self._candidates:
                meta = self._conf_meta.get(lemma, {})
                confidence = float(meta.get("confidence", 0.0))
                reason = meta.get("reason", "")
                surface = meta.get("surface", lemma)

                entry = offline_dict.lookup(lemma) or {}
                reading = entry.get("reading", "")
                meanings: list[str] = entry.get("meanings", [])
                meaning = meanings[0] if meanings else ""

                flags: list[str] = []
                if not entry:
                    flags.append("OOV")
                if is_sfx_token(lemma):
                    flags.append("SFX")
                if confidence < _CONF_HIGH or reason == "surface_fallback":
                    flags.append("low-conf")

                jlpt_level = jlpt.level_tag(lemma)
                approved = lemma not in self._known_words and lemma not in self._seen_words

                rows.append(_CandidateRow(
                    lemma=lemma,
                    surface=surface,
                    reading=reading,
                    meaning=meaning,
                    confidence=confidence,
                    confidence_reason=reason,
                    jlpt_level=jlpt_level,
                    flags=flags,
                    approved=approved,
                ))
            self.finished.emit(rows)

    # -----------------------------------------------------------------------
    # Custom table item for numeric sort on the Confidence column
    # -----------------------------------------------------------------------

    class _NumericItem(QTableWidgetItem):
        """QTableWidgetItem that sorts numerically using UserRole data."""

        def __lt__(self, other: QTableWidgetItem) -> bool:
            my_val = self.data(Qt.ItemDataRole.UserRole)
            other_val = other.data(Qt.ItemDataRole.UserRole)
            if my_val is not None and other_val is not None:
                return my_val < other_val
            return super().__lt__(other)

    # -----------------------------------------------------------------------
    # ReviewPanel
    # -----------------------------------------------------------------------

    _COL_APPROVE = 0
    _COL_SURFACE = 1
    _COL_LEMMA = 2
    _COL_READING = 3
    _COL_MEANING = 4
    _COL_CONF = 5
    _COL_JLPT = 6
    _COL_FLAGS = 7
    _NUM_COLS = 8

    _HEADERS = ["✓", "Surface", "Lemma", "Reading", "Meaning", "Conf", "JLPT", "Flags"]

    _PANEL_STYLE = """
QWidget {
    background: transparent;
}
QFrame#outerFrame {
    background-color: rgba(28, 28, 36, 255);
    border-radius: 8px;
}
QTableWidget {
    background: rgba(20, 20, 28, 255);
    alternate-background-color: rgba(30, 30, 40, 255);
    color: #DDDDDD;
    gridline-color: rgba(255,255,255,20);
    border: 1px solid rgba(255,255,255,25);
    border-radius: 4px;
    selection-background-color: rgba(34, 102, 204, 160);
}
QHeaderView::section {
    background: rgba(40, 40, 52, 255);
    color: #AAAAAA;
    padding: 4px 6px;
    border: none;
    border-right: 1px solid rgba(255,255,255,15);
    font-size: 11px;
}
QLineEdit {
    background: rgba(255,255,255,12);
    color: #FFFFFF;
    border: 1px solid rgba(255,255,255,30);
    border-radius: 4px;
    padding: 4px 8px;
}
QPushButton {
    color: #FFFFFF;
    border: none;
    border-radius: 4px;
    padding: 4px 10px;
    font-size: 11px;
    background: rgba(255,255,255,15);
}
QPushButton:hover { background: rgba(255,255,255,28); }
QPushButton:disabled { color: #555555; background: rgba(255,255,255,8); }
QLabel { color: #AAAAAA; background: transparent; font-size: 11px; }
"""

    class ReviewPanel(QWidget):
        """Interactive word review interface for batch scan results.

        Displays candidates from a scan.json as a sortable, filterable table.
        Emits ``review_completed`` with the list of approved lemmas when the
        user finalises their review.
        """

        review_completed = Signal(list)  # list[str] of approved lemmas

        def __init__(self, data_dir: str = "data", parent: QWidget | None = None) -> None:
            super().__init__(parent)
            self._data_dir = data_dir
            self._rows: list[_CandidateRow] = []
            self._source: str = ""
            self._scan_path: Path | None = None
            self._setup_ui()

        # ------------------------------------------------------------------
        # Public API
        # ------------------------------------------------------------------

        def load_candidates(self, scan_path: Path, source: str) -> None:
            """Load candidates from *scan_path* and enrich in a background thread."""
            self._scan_path = scan_path
            self._source = source

            candidates, conf_meta = _load_scan_data(scan_path)

            data_dir_path = scan_path.parent.parent.parent
            known_path = data_dir_path / source / "known_words.txt"
            seen_path = data_dir_path / source / "seen_words.json"
            known_words = _load_known_words(known_path)
            seen_words = _load_seen_words(seen_path)

            self._enrich_worker = _CandidateEnrichWorker(
                candidates=candidates,
                conf_meta=conf_meta,
                data_dir=str(data_dir_path),
                known_words=known_words,
                seen_words=seen_words,
            )
            self._enrich_worker.finished.connect(self._on_enrich_finished)
            self._enrich_worker.start()

        def _on_enrich_finished(self, rows: list) -> None:
            """Populate the table once background enrichment completes."""
            self._rows = rows
            self._populate_table()
            self._update_count_label()

        def wait_for_load(self, timeout_ms: int = 10000) -> None:
            """Block until the background enrichment worker finishes.

            Intended for tests — processes Qt events so signals are delivered.
            """
            worker = getattr(self, "_enrich_worker", None)
            if worker is None or not worker.isRunning():
                QApplication.processEvents()
                return
            worker.wait(timeout_ms)
            QApplication.processEvents()

        def approved_lemmas(self) -> list[str]:
            """Return list of currently approved lemmas (checkbox checked)."""
            result = []
            for row_idx in range(self._table.rowCount()):
                item = self._table.item(row_idx, _COL_APPROVE)
                if item and item.checkState() == Qt.CheckState.Checked:
                    lemma_item = self._table.item(row_idx, _COL_LEMMA)
                    if lemma_item:
                        result.append(lemma_item.text())
            return result

        # ------------------------------------------------------------------
        # UI setup
        # ------------------------------------------------------------------

        def _setup_ui(self) -> None:
            self.setStyleSheet(_PANEL_STYLE)

            outer_layout = QVBoxLayout(self)
            outer_layout.setContentsMargins(0, 0, 0, 0)

            frame = QFrame()
            frame.setObjectName("outerFrame")
            outer_layout.addWidget(frame)

            inner = QVBoxLayout(frame)
            inner.setContentsMargins(10, 10, 10, 10)
            inner.setSpacing(8)

            # Filter bar + count
            filter_row = QHBoxLayout()
            filter_row.setSpacing(8)

            self._search_bar = QLineEdit()
            self._search_bar.setPlaceholderText("Filter candidates…")
            self._search_bar.textChanged.connect(self._on_filter_changed)
            filter_row.addWidget(self._search_bar)

            self._count_label = QLabel("0 / 0 approved")
            self._count_label.setFixedWidth(130)
            self._count_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            filter_row.addWidget(self._count_label)

            inner.addLayout(filter_row)

            # Bulk action buttons
            bulk_row = QHBoxLayout()
            bulk_row.setSpacing(6)

            self._approve_all_btn = QPushButton("Approve All")
            self._reject_oov_btn = QPushButton("Reject OOV")
            self._approve_n3_btn = QPushButton("Approve N3+")
            self._reject_sfx_btn = QPushButton("Reject SFX")
            self._add_known_btn = QPushButton("Add Rejected → Known")
            self._finish_btn = QPushButton("Finish Review")
            self._finish_btn.setStyleSheet(
                "QPushButton { background: #2266CC; color: #FFF; border-radius: 4px;"
                " padding: 4px 12px; font-size: 11px; }"
                "QPushButton:hover { background: #1A4A99; }"
            )

            for btn in (
                self._approve_all_btn,
                self._reject_oov_btn,
                self._approve_n3_btn,
                self._reject_sfx_btn,
                self._add_known_btn,
            ):
                bulk_row.addWidget(btn)

            bulk_row.addStretch()
            bulk_row.addWidget(self._finish_btn)

            self._approve_all_btn.clicked.connect(self._on_approve_all)
            self._reject_oov_btn.clicked.connect(self._on_reject_oov)
            self._approve_n3_btn.clicked.connect(self._on_approve_n3_plus)
            self._reject_sfx_btn.clicked.connect(self._on_reject_sfx)
            self._add_known_btn.clicked.connect(self._on_add_to_known)
            self._finish_btn.clicked.connect(self._on_finish)

            inner.addLayout(bulk_row)

            # Table
            self._table = QTableWidget(0, _NUM_COLS)
            self._table.setHorizontalHeaderLabels(_HEADERS)
            self._table.setSortingEnabled(True)
            self._table.setAlternatingRowColors(True)
            self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
            self._table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)

            hdr = self._table.horizontalHeader()
            hdr.setStretchLastSection(False)
            # Column widths
            self._table.setColumnWidth(_COL_APPROVE, 30)
            self._table.setColumnWidth(_COL_SURFACE, 80)
            self._table.setColumnWidth(_COL_LEMMA, 90)
            self._table.setColumnWidth(_COL_READING, 90)
            self._table.setColumnWidth(_COL_MEANING, 200)
            self._table.setColumnWidth(_COL_CONF, 55)
            self._table.setColumnWidth(_COL_JLPT, 45)
            self._table.setColumnWidth(_COL_FLAGS, 100)

            self._table.itemChanged.connect(self._on_item_changed)
            inner.addWidget(self._table, stretch=1)

        # ------------------------------------------------------------------
        # Table population
        # ------------------------------------------------------------------

        def _populate_table(self) -> None:
            self._table.setSortingEnabled(False)
            self._table.setRowCount(0)
            self._table.setRowCount(len(self._rows))

            for row_idx, row in enumerate(self._rows):
                self._set_row(row_idx, row)

            self._table.setSortingEnabled(True)
            self._apply_filter(self._search_bar.text())

        def _set_row(self, row_idx: int, row: _CandidateRow) -> None:
            tier = _confidence_tier(row)
            bg_color = QColor(
                _COLOR_HIGH if tier == "high" else
                _COLOR_MID if tier == "mid" else
                _COLOR_LOW
            )

            def _make_item(text: str, align: Qt.AlignmentFlag = Qt.AlignmentFlag.AlignVCenter) -> QTableWidgetItem:
                item = QTableWidgetItem(text)
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                item.setBackground(bg_color)
                return item

            # Checkbox column
            chk_item = QTableWidgetItem()
            chk_item.setFlags(
                Qt.ItemFlag.ItemIsEnabled
                | Qt.ItemFlag.ItemIsUserCheckable
                | Qt.ItemFlag.ItemIsSelectable
            )
            chk_item.setCheckState(
                Qt.CheckState.Checked if row.approved else Qt.CheckState.Unchecked
            )
            chk_item.setBackground(bg_color)
            self._table.setItem(row_idx, _COL_APPROVE, chk_item)

            self._table.setItem(row_idx, _COL_SURFACE, _make_item(row.surface))
            self._table.setItem(row_idx, _COL_LEMMA, _make_item(row.lemma))
            self._table.setItem(row_idx, _COL_READING, _make_item(row.reading))
            self._table.setItem(row_idx, _COL_MEANING, _make_item(row.meaning))

            # Confidence — numeric sort via UserRole
            conf_item = _NumericItem(f"{row.confidence:.2f}")
            conf_item.setData(Qt.ItemDataRole.UserRole, row.confidence)
            conf_item.setFlags(conf_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            conf_item.setBackground(bg_color)
            conf_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignVCenter)
            self._table.setItem(row_idx, _COL_CONF, conf_item)

            self._table.setItem(row_idx, _COL_JLPT, _make_item(row.jlpt_level))
            self._table.setItem(row_idx, _COL_FLAGS, _make_item(", ".join(row.flags)))

        # ------------------------------------------------------------------
        # Filter
        # ------------------------------------------------------------------

        def _apply_filter(self, text: str) -> None:
            needle = text.strip().lower()
            for row_idx in range(self._table.rowCount()):
                if not needle:
                    self._table.setRowHidden(row_idx, False)
                    continue
                lemma_item = self._table.item(row_idx, _COL_LEMMA)
                surface_item = self._table.item(row_idx, _COL_SURFACE)
                lemma_text = lemma_item.text().lower() if lemma_item else ""
                surface_text = surface_item.text().lower() if surface_item else ""
                self._table.setRowHidden(row_idx, needle not in lemma_text and needle not in surface_text)

        def _on_filter_changed(self, text: str) -> None:
            self._apply_filter(text)

        # ------------------------------------------------------------------
        # Bulk actions
        # ------------------------------------------------------------------

        def _set_all_visible_checked(self, checked: bool) -> None:
            self._table.blockSignals(True)
            for row_idx in range(self._table.rowCount()):
                if self._table.isRowHidden(row_idx):
                    continue
                item = self._table.item(row_idx, _COL_APPROVE)
                if item:
                    item.setCheckState(
                        Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked
                    )
            self._table.blockSignals(False)
            self._update_count_label()

        def _on_approve_all(self) -> None:
            self._set_all_visible_checked(True)

        def _on_reject_oov(self) -> None:
            self._table.blockSignals(True)
            for row_idx in range(self._table.rowCount()):
                if self._table.isRowHidden(row_idx):
                    continue
                flags_item = self._table.item(row_idx, _COL_FLAGS)
                if flags_item and "OOV" in flags_item.text():
                    item = self._table.item(row_idx, _COL_APPROVE)
                    if item:
                        item.setCheckState(Qt.CheckState.Unchecked)
            self._table.blockSignals(False)
            self._update_count_label()

        def _on_approve_n3_plus(self) -> None:
            self._table.blockSignals(True)
            for row_idx in range(self._table.rowCount()):
                if self._table.isRowHidden(row_idx):
                    continue
                jlpt_item = self._table.item(row_idx, _COL_JLPT)
                if jlpt_item and jlpt_item.text() in _COMMON_JLPT_LEVELS:
                    item = self._table.item(row_idx, _COL_APPROVE)
                    if item:
                        item.setCheckState(Qt.CheckState.Checked)
            self._table.blockSignals(False)
            self._update_count_label()

        def _on_reject_sfx(self) -> None:
            self._table.blockSignals(True)
            for row_idx in range(self._table.rowCount()):
                if self._table.isRowHidden(row_idx):
                    continue
                flags_item = self._table.item(row_idx, _COL_FLAGS)
                if flags_item and "SFX" in flags_item.text():
                    item = self._table.item(row_idx, _COL_APPROVE)
                    if item:
                        item.setCheckState(Qt.CheckState.Unchecked)
            self._table.blockSignals(False)
            self._update_count_label()

        def _on_add_to_known(self) -> None:
            if not self._source or self._scan_path is None:
                return
            data_dir_path = self._scan_path.parent.parent.parent
            known_path = data_dir_path / self._source / "known_words.txt"

            rejected: set[str] = set()
            for row_idx in range(self._table.rowCount()):
                item = self._table.item(row_idx, _COL_APPROVE)
                if item and item.checkState() == Qt.CheckState.Unchecked:
                    lemma_item = self._table.item(row_idx, _COL_LEMMA)
                    if lemma_item:
                        rejected.add(lemma_item.text())

            if rejected:
                _append_known_words(known_path, rejected)
                logger.info("Added %d rejected words to known_words.txt", len(rejected))

        def _on_finish(self) -> None:
            approved = self.approved_lemmas()
            self.review_completed.emit(approved)

        # ------------------------------------------------------------------
        # State tracking
        # ------------------------------------------------------------------

        def _on_item_changed(self, item: QTableWidgetItem) -> None:
            if item.column() == _COL_APPROVE:
                self._update_count_label()

        def _update_count_label(self) -> None:
            total = sum(
                1 for row_idx in range(self._table.rowCount())
                if not self._table.isRowHidden(row_idx)
            )
            approved = sum(
                1
                for row_idx in range(self._table.rowCount())
                if not self._table.isRowHidden(row_idx)
                and self._table.item(row_idx, _COL_APPROVE) is not None
                and self._table.item(row_idx, _COL_APPROVE).checkState() == Qt.CheckState.Checked
            )
            self._count_label.setText(f"{approved} / {total} approved")

except ImportError:
    class ReviewPanel:  # type: ignore[no-redef]
        """Stub used when PySide6 is not installed."""

        def __init__(self, data_dir: str = "data", parent: object = None) -> None:
            raise ImportError(
                "ReviewPanel requires PySide6. Install with: pip install PySide6"
            )

        def load_candidates(self, scan_path: Path, source: str) -> None:
            raise ImportError("ReviewPanel requires PySide6.")

        def approved_lemmas(self) -> list[str]:
            raise ImportError("ReviewPanel requires PySide6.")
