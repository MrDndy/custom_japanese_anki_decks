from __future__ import annotations

import zipfile
from pathlib import Path

import pytest

from jp_anki_builder.lookup_service import LookupResult
from jp_anki_builder.realtime.session import SessionBuffer, SessionWord


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _result(
    surface="食べる",
    dictionary_form="食べる",
    reading="たべる",
    meanings=None,
    jlpt_level="N4",
) -> LookupResult:
    return LookupResult(
        surface=surface,
        dictionary_form=dictionary_form,
        reading=reading,
        meanings=meanings or ["to eat", "to consume"],
        part_of_speech="動詞",
        confidence=0.99,
        jlpt_level=jlpt_level,
        is_in_vocab_db=False,
    )


# ---------------------------------------------------------------------------
# Add / get / len
# ---------------------------------------------------------------------------

class TestAddAndGet:
    def test_add_word_returns_true(self):
        buf = SessionBuffer()
        assert buf.add_word(_result(), "テスト文") is True

    def test_get_words_returns_added_words(self):
        buf = SessionBuffer()
        buf.add_word(_result(), "テスト文")
        words = buf.get_words()
        assert len(words) == 1
        assert isinstance(words[0], SessionWord)
        assert words[0].dictionary_form == "食べる"
        assert words[0].reading == "たべる"
        assert words[0].source_context == "テスト文"

    def test_len_reflects_buffer_size(self):
        buf = SessionBuffer()
        assert len(buf) == 0
        buf.add_word(_result(), "")
        assert len(buf) == 1

    def test_added_at_is_iso_datetime(self):
        buf = SessionBuffer()
        buf.add_word(_result(), "")
        word = buf.get_words()[0]
        # ISO format: YYYY-MM-DDTHH:MM:SS...
        assert "T" in word.added_at

    def test_get_words_returns_copy(self):
        buf = SessionBuffer()
        buf.add_word(_result(), "")
        words = buf.get_words()
        words.clear()
        assert len(buf) == 1  # original unaffected


# ---------------------------------------------------------------------------
# Dedup
# ---------------------------------------------------------------------------

class TestDedup:
    def test_duplicate_form_reading_rejected(self):
        buf = SessionBuffer()
        buf.add_word(_result(dictionary_form="食べる", reading="たべる"), "")
        assert buf.add_word(_result(dictionary_form="食べる", reading="たべる"), "") is False
        assert len(buf) == 1

    def test_same_form_different_reading_allowed(self):
        buf = SessionBuffer()
        buf.add_word(_result(dictionary_form="行く", reading="いく"), "")
        assert buf.add_word(_result(dictionary_form="行く", reading="ゆく"), "") is True
        assert len(buf) == 2

    def test_different_form_same_reading_allowed(self):
        buf = SessionBuffer()
        buf.add_word(_result(dictionary_form="食べる", reading="たべる"), "")
        assert buf.add_word(_result(dictionary_form="食う", reading="たべる"), "") is True
        assert len(buf) == 2


# ---------------------------------------------------------------------------
# Remove
# ---------------------------------------------------------------------------

class TestRemove:
    def test_remove_by_index(self):
        buf = SessionBuffer()
        buf.add_word(_result(dictionary_form="食べる"), "")
        buf.add_word(_result(dictionary_form="行く", reading="いく"), "")
        buf.remove_word(0)
        assert len(buf) == 1
        assert buf.get_words()[0].dictionary_form == "行く"

    def test_remove_allows_readd(self):
        buf = SessionBuffer()
        buf.add_word(_result(dictionary_form="食べる", reading="たべる"), "")
        buf.remove_word(0)
        assert buf.add_word(_result(dictionary_form="食べる", reading="たべる"), "") is True

    def test_remove_out_of_range_is_noop(self):
        buf = SessionBuffer()
        buf.add_word(_result(), "")
        buf.remove_word(5)
        assert len(buf) == 1

    def test_remove_negative_is_noop(self):
        buf = SessionBuffer()
        buf.add_word(_result(), "")
        buf.remove_word(-1)
        assert len(buf) == 1


# ---------------------------------------------------------------------------
# Clear
# ---------------------------------------------------------------------------

class TestClear:
    def test_clear_empties_buffer(self):
        buf = SessionBuffer()
        buf.add_word(_result(), "")
        buf.clear()
        assert len(buf) == 0
        assert buf.get_words() == []

    def test_clear_resets_dedup(self):
        buf = SessionBuffer()
        buf.add_word(_result(), "")
        buf.clear()
        assert buf.add_word(_result(), "") is True


# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------

class TestExportDeck:
    def test_export_generates_apkg_file(self, tmp_path):
        buf = SessionBuffer(data_dir=str(tmp_path))
        buf.add_word(_result(), "テスト文")
        path = buf.export_deck("test_deck")
        assert path.exists()
        assert path.suffix == ".apkg"

    def test_exported_apkg_is_valid_zip(self, tmp_path):
        buf = SessionBuffer(data_dir=str(tmp_path))
        buf.add_word(_result(), "")
        path = buf.export_deck("test_deck")
        assert zipfile.is_zipfile(path)

    def test_export_with_volume_and_chapter(self, tmp_path):
        buf = SessionBuffer(data_dir=str(tmp_path))
        buf.add_word(_result(), "")
        path = buf.export_deck("manga", volume="1", chapter="5")
        assert path.exists()

    def test_export_updates_vocab_db(self, tmp_path):
        import sqlite3

        buf = SessionBuffer(data_dir=str(tmp_path))
        buf.add_word(_result(dictionary_form="食べる", reading="たべる"), "")
        buf.export_deck("test_deck")

        db_path = tmp_path / "vocabulary.db"
        assert db_path.exists()
        conn = sqlite3.connect(str(db_path))
        row = conn.execute(
            "SELECT expression, reading FROM vocabulary WHERE expression = ?",
            ("食べる",),
        ).fetchone()
        conn.close()
        assert row is not None
        assert row[0] == "食べる"

    def test_export_empty_buffer_raises(self, tmp_path):
        buf = SessionBuffer(data_dir=str(tmp_path))
        with pytest.raises(ValueError, match="empty"):
            buf.export_deck("test_deck")

    def test_export_multiple_words(self, tmp_path):
        buf = SessionBuffer(data_dir=str(tmp_path))
        buf.add_word(_result(dictionary_form="食べる", reading="たべる"), "")
        buf.add_word(_result(dictionary_form="行く", reading="いく", meanings=["to go"]), "")
        path = buf.export_deck("test_deck")
        assert path.exists()

    def test_export_path_in_realtime_sessions_dir(self, tmp_path):
        buf = SessionBuffer(data_dir=str(tmp_path))
        buf.add_word(_result(), "")
        path = buf.export_deck("test_deck")
        assert "realtime_sessions" in str(path)
