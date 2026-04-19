from __future__ import annotations

import json
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Helper — build minimal scan.json fixture
# ---------------------------------------------------------------------------

def _write_scan_json(path: Path, candidates: list[str], norm_records: list[dict] | None = None) -> None:
    norm_records = norm_records or []
    payload = {
        "source": "testshow",
        "run_id": "ep01",
        "ocr_mode": "subtitle",
        "candidates": candidates,
        "records": [{"image": "line_0000", "text": "...", "normalized_candidates": norm_records}],
    }
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def _norm(lemma: str, surface: str = "", confidence: float = 0.95, reason: str = "dict_lookup") -> dict:
    return {"lemma": lemma, "surface": surface or lemma, "confidence": confidence, "reason": reason}


# ---------------------------------------------------------------------------
# Non-GUI unit tests for helpers
# ---------------------------------------------------------------------------

class TestLoadScanData:
    def test_returns_candidates(self, tmp_path):
        from jp_anki_builder.gui.review_panel import _load_scan_data

        scan_path = tmp_path / "scan.json"
        _write_scan_json(scan_path, ["食べる", "走る"])
        candidates, meta = _load_scan_data(scan_path)
        assert "食べる" in candidates
        assert "走る" in candidates

    def test_builds_confidence_meta(self, tmp_path):
        from jp_anki_builder.gui.review_panel import _load_scan_data

        scan_path = tmp_path / "scan.json"
        _write_scan_json(
            scan_path,
            ["食べる"],
            norm_records=[_norm("食べる", confidence=0.95, reason="dict_lookup")],
        )
        _, meta = _load_scan_data(scan_path)
        assert "食べる" in meta
        assert meta["食べる"]["confidence"] == pytest.approx(0.95)
        assert meta["食べる"]["reason"] == "dict_lookup"

    def test_picks_best_confidence(self, tmp_path):
        from jp_anki_builder.gui.review_panel import _load_scan_data

        scan_path = tmp_path / "scan.json"
        payload = {
            "candidates": ["食べる"],
            "records": [
                {"normalized_candidates": [_norm("食べる", confidence=0.6)]},
                {"normalized_candidates": [_norm("食べる", confidence=0.95)]},
            ],
        }
        scan_path.write_text(json.dumps(payload), encoding="utf-8")
        _, meta = _load_scan_data(scan_path)
        assert meta["食べる"]["confidence"] == pytest.approx(0.95)


class TestConfidenceTier:
    def test_high_tier(self):
        from jp_anki_builder.gui.review_panel import _CandidateRow, _confidence_tier

        row = _CandidateRow("食べる", "食べ", "", "", 0.95, "dict_lookup", "N5", [])
        assert _confidence_tier(row) == "high"

    def test_mid_tier(self):
        from jp_anki_builder.gui.review_panel import _CandidateRow, _confidence_tier

        row = _CandidateRow("走る", "走", "", "", 0.75, "deinflection", "", [])
        assert _confidence_tier(row) == "mid"

    def test_low_tier_surface_fallback(self):
        from jp_anki_builder.gui.review_panel import _CandidateRow, _confidence_tier

        row = _CandidateRow("ドドド", "ドドド", "", "", 0.5, "surface_fallback", "", ["OOV"])
        assert _confidence_tier(row) == "low"

    def test_oov_forces_low(self):
        from jp_anki_builder.gui.review_panel import _CandidateRow, _confidence_tier

        row = _CandidateRow("謎語", "謎語", "", "", 0.95, "dict_lookup", "", ["OOV"])
        assert _confidence_tier(row) == "low"


class TestKnownWordsHelpers:
    def test_load_known_words_missing_file(self, tmp_path):
        from jp_anki_builder.gui.review_panel import _load_known_words

        result = _load_known_words(tmp_path / "no_such_file.txt")
        assert result == set()

    def test_load_known_words_reads_lines(self, tmp_path):
        from jp_anki_builder.gui.review_panel import _load_known_words

        f = tmp_path / "known.txt"
        f.write_text("食べる\n走る\n", encoding="utf-8")
        result = _load_known_words(f)
        assert "食べる" in result
        assert "走る" in result

    def test_append_known_words_creates_file(self, tmp_path):
        from jp_anki_builder.gui.review_panel import _append_known_words

        f = tmp_path / "known.txt"
        _append_known_words(f, {"飲む"})
        assert "飲む" in f.read_text(encoding="utf-8")

    def test_append_known_words_merges(self, tmp_path):
        from jp_anki_builder.gui.review_panel import _append_known_words

        f = tmp_path / "known.txt"
        f.write_text("食べる\n", encoding="utf-8")
        _append_known_words(f, {"走る"})
        content = f.read_text(encoding="utf-8")
        assert "食べる" in content
        assert "走る" in content


# ---------------------------------------------------------------------------
# GUI tests (require PySide6 + display)
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def qt_app():
    pytest.importorskip("PySide6")
    try:
        from PySide6.QtWidgets import QApplication
        import sys
        app = QApplication.instance() or QApplication(sys.argv)
        yield app
    except Exception:
        pytest.skip("Cannot create QApplication (no display)")


@pytest.mark.gui
class TestReviewPanelGUI:
    def _make_scan(self, tmp_path: Path, words: list[tuple[str, float, str]]) -> Path:
        """words = list of (lemma, confidence, reason)"""
        candidates = [w[0] for w in words]
        norm = [_norm(w[0], confidence=w[1], reason=w[2]) for w in words]
        scan_path = tmp_path / "testshow" / "ep01" / "scan.json"
        scan_path.parent.mkdir(parents=True, exist_ok=True)
        _write_scan_json(scan_path, candidates, norm)
        return scan_path

    def test_creates_without_error(self, qt_app, tmp_path):
        from jp_anki_builder.gui.review_panel import ReviewPanel

        panel = ReviewPanel(data_dir=str(tmp_path))
        assert panel is not None

    def test_load_candidates_populates_table(self, qt_app, tmp_path):
        from jp_anki_builder.gui.review_panel import ReviewPanel

        scan_path = self._make_scan(tmp_path, [
            ("食べる", 0.95, "dict_lookup"),
            ("走る", 0.80, "deinflection"),
        ])
        panel = ReviewPanel(data_dir=str(tmp_path))
        panel.load_candidates(scan_path, "testshow")
        panel.wait_for_load()
        assert panel._table.rowCount() == 2

    def test_all_approved_by_default(self, qt_app, tmp_path):
        from PySide6.QtCore import Qt
        from jp_anki_builder.gui.review_panel import ReviewPanel

        scan_path = self._make_scan(tmp_path, [("食べる", 0.95, "dict_lookup")])
        panel = ReviewPanel(data_dir=str(tmp_path))
        panel.load_candidates(scan_path, "testshow")
        panel.wait_for_load()

        item = panel._table.item(0, 0)  # checkbox column
        assert item.checkState() == Qt.CheckState.Checked

    def test_approved_lemmas_returns_checked(self, qt_app, tmp_path):
        from jp_anki_builder.gui.review_panel import ReviewPanel

        scan_path = self._make_scan(tmp_path, [
            ("食べる", 0.95, "dict_lookup"),
            ("走る", 0.80, "deinflection"),
        ])
        panel = ReviewPanel(data_dir=str(tmp_path))
        panel.load_candidates(scan_path, "testshow")
        panel.wait_for_load()

        approved = panel.approved_lemmas()
        assert "食べる" in approved
        assert "走る" in approved

    def test_approve_all_checks_all_visible(self, qt_app, tmp_path):
        from PySide6.QtCore import Qt
        from jp_anki_builder.gui.review_panel import ReviewPanel, _COL_APPROVE

        scan_path = self._make_scan(tmp_path, [
            ("食べる", 0.95, "dict_lookup"),
            ("走る", 0.80, "deinflection"),
        ])
        panel = ReviewPanel(data_dir=str(tmp_path))
        panel.load_candidates(scan_path, "testshow")
        panel.wait_for_load()

        # Uncheck first
        panel._table.item(0, _COL_APPROVE).setCheckState(Qt.CheckState.Unchecked)
        panel._on_approve_all()

        for row_idx in range(panel._table.rowCount()):
            assert panel._table.item(row_idx, _COL_APPROVE).checkState() == Qt.CheckState.Checked

    def test_reject_oov_unchecks_oov_rows(self, qt_app, tmp_path):
        from PySide6.QtCore import Qt
        from jp_anki_builder.gui.review_panel import (
            ReviewPanel, _COL_APPROVE, _COL_FLAGS, QTableWidgetItem
        )

        scan_path = self._make_scan(tmp_path, [("ドドド", 0.3, "surface_fallback")])
        panel = ReviewPanel(data_dir=str(tmp_path))
        panel.load_candidates(scan_path, "testshow")
        panel.wait_for_load()

        # Manually mark as OOV if not already
        flags_item = panel._table.item(0, _COL_FLAGS)
        if flags_item and "OOV" not in flags_item.text():
            flags_item.setText("OOV")

        panel._on_reject_oov()
        # OOV rows should be unchecked
        item = panel._table.item(0, _COL_APPROVE)
        assert item.checkState() == Qt.CheckState.Unchecked

    def test_search_filter_hides_non_matching(self, qt_app, tmp_path):
        from jp_anki_builder.gui.review_panel import ReviewPanel

        scan_path = self._make_scan(tmp_path, [
            ("食べる", 0.95, "dict_lookup"),
            ("走る", 0.80, "deinflection"),
        ])
        panel = ReviewPanel(data_dir=str(tmp_path))
        panel.load_candidates(scan_path, "testshow")
        panel.wait_for_load()

        panel._search_bar.setText("食べ")

        # At least one row should be hidden
        hidden_count = sum(
            1 for i in range(panel._table.rowCount())
            if panel._table.isRowHidden(i)
        )
        assert hidden_count >= 1

    def test_count_label_updates(self, qt_app, tmp_path):
        from PySide6.QtCore import Qt
        from jp_anki_builder.gui.review_panel import ReviewPanel, _COL_APPROVE

        scan_path = self._make_scan(tmp_path, [
            ("食べる", 0.95, "dict_lookup"),
            ("走る", 0.80, "deinflection"),
        ])
        panel = ReviewPanel(data_dir=str(tmp_path))
        panel.load_candidates(scan_path, "testshow")
        panel.wait_for_load()

        panel._table.item(0, _COL_APPROVE).setCheckState(Qt.CheckState.Unchecked)
        panel._update_count_label()
        assert "1 / 2" in panel._count_label.text()

    def test_finish_emits_review_completed(self, qt_app, tmp_path):
        from jp_anki_builder.gui.review_panel import ReviewPanel

        scan_path = self._make_scan(tmp_path, [("食べる", 0.95, "dict_lookup")])
        panel = ReviewPanel(data_dir=str(tmp_path))
        panel.load_candidates(scan_path, "testshow")
        panel.wait_for_load()

        emitted: list[list[str]] = []
        panel.review_completed.connect(lambda lst: emitted.append(lst))
        panel._on_finish()

        assert len(emitted) == 1
        assert "食べる" in emitted[0]

    def test_add_to_known_writes_file(self, qt_app, tmp_path):
        from PySide6.QtCore import Qt
        from jp_anki_builder.gui.review_panel import ReviewPanel, _COL_APPROVE

        scan_path = self._make_scan(tmp_path, [("食べる", 0.95, "dict_lookup")])
        panel = ReviewPanel(data_dir=str(tmp_path))
        panel.load_candidates(scan_path, "testshow")
        panel.wait_for_load()

        # Reject the word
        panel._table.item(0, _COL_APPROVE).setCheckState(Qt.CheckState.Unchecked)
        panel._on_add_to_known()

        known_path = tmp_path / "testshow" / "known_words.txt"
        assert known_path.exists()
        assert "食べる" in known_path.read_text(encoding="utf-8")
