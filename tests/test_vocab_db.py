from __future__ import annotations

import sqlite3
import tempfile
import shutil
from pathlib import Path

import pytest

from jp_anki_builder.vocab_db import VocabDB


class TestVocabDB:
    def setup_method(self):
        self._tmp = tempfile.mkdtemp()
        self.db_path = Path(self._tmp) / "vocabulary.db"
        self.db = VocabDB(self.db_path)

    def teardown_method(self):
        self.db.close()
        shutil.rmtree(self._tmp, ignore_errors=True)

    def test_db_file_created_on_init(self):
        assert self.db_path.exists()

    def test_schema_tables_exist(self):
        conn = sqlite3.connect(str(self.db_path))
        tables = {row[0] for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()}
        conn.close()
        assert "vocabulary" in tables
        assert "export_history" in tables

    def test_insert_word(self):
        words = [{"word": "勇者", "reading": "ゆうしゃ"}]
        count = self.db.record_exports(words, deck_name="TestDeck", source="manga-a")
        assert count == 1

        conn = sqlite3.connect(str(self.db_path))
        row = conn.execute(
            "SELECT expression, reading, export_count FROM vocabulary WHERE expression = ?",
            ("勇者",),
        ).fetchone()
        conn.close()
        assert row == ("勇者", "ゆうしゃ", 1)

    def test_duplicate_upserts_increments_export_count(self):
        words = [{"word": "冒険", "reading": "ぼうけん"}]
        self.db.record_exports(words, deck_name="Deck1", source="manga-a")
        self.db.record_exports(words, deck_name="Deck2", source="manga-a")

        conn = sqlite3.connect(str(self.db_path))
        row = conn.execute(
            "SELECT export_count FROM vocabulary WHERE expression = ?", ("冒険",)
        ).fetchone()
        conn.close()
        assert row[0] == 2

    def test_duplicate_does_not_raise(self):
        words = [{"word": "走る", "reading": "はしる"}]
        # Should not raise even when called multiple times
        self.db.record_exports(words, deck_name="D", source="src")
        self.db.record_exports(words, deck_name="D", source="src")

    def test_export_history_recorded(self):
        words = [{"word": "魔法", "reading": "まほう"}]
        self.db.record_exports(words, deck_name="MyDeck", source="game-a")

        conn = sqlite3.connect(str(self.db_path))
        rows = conn.execute(
            "SELECT deck_name, source_context FROM export_history"
        ).fetchall()
        conn.close()
        assert len(rows) == 1
        assert rows[0] == ("MyDeck", "game-a")

    def test_multiple_export_history_entries_for_same_word(self):
        words = [{"word": "剣", "reading": "けん"}]
        self.db.record_exports(words, deck_name="Vol1", source="manga-a")
        self.db.record_exports(words, deck_name="Vol2", source="manga-a")

        conn = sqlite3.connect(str(self.db_path))
        history = conn.execute(
            "SELECT deck_name FROM export_history ORDER BY id"
        ).fetchall()
        conn.close()
        assert [r[0] for r in history] == ["Vol1", "Vol2"]

    def test_empty_word_skipped(self):
        words = [{"word": "", "reading": ""}, {"word": "謎", "reading": "なぞ"}]
        count = self.db.record_exports(words, deck_name="D", source="src")
        assert count == 1

    def test_missing_reading_treated_as_empty_string(self):
        words = [{"word": "謎"}]  # no "reading" key
        count = self.db.record_exports(words, deck_name="D", source="src")
        assert count == 1

        conn = sqlite3.connect(str(self.db_path))
        row = conn.execute(
            "SELECT reading FROM vocabulary WHERE expression = ?", ("謎",)
        ).fetchone()
        conn.close()
        assert row[0] == ""
