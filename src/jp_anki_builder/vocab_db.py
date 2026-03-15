"""Central SQLite vocabulary database for cross-source dedup tracking."""
from __future__ import annotations

import logging
import sqlite3
from datetime import date
from pathlib import Path

logger = logging.getLogger(__name__)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS vocabulary (
    id INTEGER PRIMARY KEY,
    expression TEXT NOT NULL,
    reading TEXT NOT NULL,
    first_seen_source TEXT,
    first_seen_date TEXT,
    export_count INTEGER DEFAULT 0,
    UNIQUE(expression, reading)
);

CREATE TABLE IF NOT EXISTS export_history (
    id INTEGER PRIMARY KEY,
    vocabulary_id INTEGER REFERENCES vocabulary(id),
    deck_name TEXT NOT NULL,
    export_date TEXT NOT NULL,
    source_context TEXT
);
"""


class VocabDB:
    """Central SQLite database tracking all exported vocabulary across sources."""

    def __init__(self, db_path: Path) -> None:
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(db_path), check_same_thread=False)
        self._conn.executescript(_SCHEMA)
        self._conn.commit()
        logger.debug("vocab db opened: %s", db_path)

    def record_exports(
        self,
        words: list[dict],
        deck_name: str,
        source: str,
    ) -> int:
        """Upsert each word into vocabulary and add export_history rows.

        Returns the number of words recorded.
        """
        today = date.today().isoformat()
        cur = self._conn.cursor()
        count = 0
        for item in words:
            expression = item.get("word", "")
            reading = item.get("reading", "") or ""
            if not expression:
                continue

            cur.execute(
                """
                INSERT INTO vocabulary
                    (expression, reading, first_seen_source, first_seen_date, export_count)
                VALUES (?, ?, ?, ?, 1)
                ON CONFLICT(expression, reading) DO UPDATE SET
                    export_count = export_count + 1
                """,
                (expression, reading, source, today),
            )
            row = cur.execute(
                "SELECT id FROM vocabulary WHERE expression = ? AND reading = ?",
                (expression, reading),
            ).fetchone()
            if row:
                cur.execute(
                    "INSERT INTO export_history"
                    " (vocabulary_id, deck_name, export_date, source_context)"
                    " VALUES (?, ?, ?, ?)",
                    (row[0], deck_name, today, source),
                )
                count += 1

        self._conn.commit()
        logger.debug("recorded %d word(s) to vocab db (deck=%s)", count, deck_name)
        return count

    def __enter__(self) -> VocabDB:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def close(self) -> None:
        self._conn.close()
