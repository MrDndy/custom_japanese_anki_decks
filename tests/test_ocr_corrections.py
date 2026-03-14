"""Tests for OCR confusable character correction."""

from jp_anki_builder.ocr_corrections import (
    correct_with_dictionary,
    ocr_correction_candidates,
)


class TestOcrCorrectionCandidates:
    def test_no_confusables_returns_empty(self):
        assert ocr_correction_candidates("走る") == []

    def test_katakana_ro_to_kanji_mouth(self):
        candidates = ocr_correction_candidates("ロボット")
        # ロ could be misread as 口
        assert "口ボット" in candidates

    def test_kanji_power_to_katakana_ka(self):
        candidates = ocr_correction_candidates("力")
        assert "カ" in candidates

    def test_prolonged_mark_vs_one(self):
        candidates = ocr_correction_candidates("ラーメン")
        # ー could be misread as 一
        assert "ラ一メン" in candidates

    def test_reverse_direction(self):
        """一 misread for ー should also generate correction."""
        candidates = ocr_correction_candidates("ラ一メン")
        assert "ラーメン" in candidates

    def test_max_candidates(self):
        candidates = ocr_correction_candidates("ロロロロロロロロロ", max_candidates=3)
        assert len(candidates) <= 3

    def test_empty_string(self):
        assert ocr_correction_candidates("") == []

    def test_dakuten_handakuten_confusion(self):
        candidates = ocr_correction_candidates("ぺん")
        assert "べん" in candidates


class TestCorrectWithDictionary:
    def _make_dict(self, words: set[str]):
        return lambda w: w in words

    def test_corrects_katakana_ro_to_kanji(self):
        """口 (mouth) misread as ロ (katakana)."""
        word_exists = self._make_dict({"口"})
        assert correct_with_dictionary("ロ", word_exists) == "口"

    def test_corrects_prolonged_mark(self):
        """一 (kanji one) misread as ー (prolonged mark)."""
        word_exists = self._make_dict({"一人"})
        assert correct_with_dictionary("ー人", word_exists) == "一人"

    def test_returns_none_when_no_match(self):
        word_exists = self._make_dict(set())
        assert correct_with_dictionary("ロボット", word_exists) is None

    def test_integration_with_normalization(self):
        """OCR correction integrates into _choose_best_candidate."""
        from jp_anki_builder.normalization import _choose_best_candidate

        word_exists = lambda w: w in {"口"}
        result, confidence, reason = _choose_best_candidate("ロ", "ロ", word_exists)
        assert result == "口"
        assert reason == "ocr_corrected"
        assert confidence == 0.93
