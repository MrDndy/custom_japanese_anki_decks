from __future__ import annotations

import json
import logging
import sqlite3
import time
from urllib.parse import quote
from urllib.request import Request, urlopen
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class OfflineJsonDictionary:
    path: Path
    _cache_payload: dict | None = None
    _cache_mtime_ns: int | None = None

    def lookup(self, word: str, exact_match: bool = False):
        payload = self._load_payload()
        if payload is None:
            return None
        hit = payload.get(word)
        if hit is not None:
            logger.debug("offline hit: %s", word)
        return hit

    def _load_payload(self) -> dict | None:
        if not self.path.exists():
            self._cache_payload = None
            self._cache_mtime_ns = None
            return None

        stat = self.path.stat()
        mtime_ns = stat.st_mtime_ns
        if self._cache_payload is not None and self._cache_mtime_ns == mtime_ns:
            return self._cache_payload

        logger.debug("loading offline dictionary from %s", self.path)
        payload = json.loads(self.path.read_text(encoding="utf-8-sig"))
        self._cache_payload = payload
        self._cache_mtime_ns = mtime_ns
        return payload


@dataclass
class OfflineSqliteDictionary:
    path: Path
    _conn: sqlite3.Connection | None = field(default=None, repr=False)

    def _get_conn(self) -> sqlite3.Connection | None:
        if self._conn is not None:
            return self._conn
        if not self.path.exists():
            return None
        self._conn = sqlite3.connect(str(self.path), check_same_thread=False)
        return self._conn

    def lookup(self, word: str, exact_match: bool = False):
        conn = self._get_conn()
        if conn is None:
            return None
        row = conn.execute(
            "SELECT reading, meanings FROM entries WHERE word = ?", (word,)
        ).fetchone()
        if row is None:
            return None
        logger.debug("sqlite hit: %s", word)
        return {"reading": row[0], "meanings": json.loads(row[1])}

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    @staticmethod
    def create_from_json(json_path: Path, sqlite_path: Path) -> int:
        """Migrate an offline.json dictionary to SQLite. Returns entry count."""
        data = json.loads(json_path.read_text(encoding="utf-8-sig"))
        sqlite_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(sqlite_path))
        conn.execute(
            "CREATE TABLE IF NOT EXISTS entries ("
            "  word TEXT PRIMARY KEY,"
            "  reading TEXT NOT NULL,"
            "  meanings TEXT NOT NULL"
            ")"
        )
        conn.execute("DELETE FROM entries")
        conn.executemany(
            "INSERT INTO entries (word, reading, meanings) VALUES (?, ?, ?)",
            [
                (word, entry["reading"], json.dumps(entry["meanings"], ensure_ascii=False))
                for word, entry in data.items()
            ],
        )
        conn.commit()
        count = conn.execute("SELECT COUNT(*) FROM entries").fetchone()[0]
        conn.close()
        logger.info("migrated %d entries from %s to %s", count, json_path, sqlite_path)
        return count


@dataclass
class NullOnlineDictionary:
    def lookup(self, word: str, exact_match: bool = False):
        return None


@dataclass
class JishoOnlineDictionary:
    timeout_seconds: int = 8
    request_delay_seconds: float = 0.2
    _last_request_time: float = field(default=0.0, repr=False)

    def lookup(self, word: str, exact_match: bool = False):
        now = time.monotonic()
        elapsed = now - self._last_request_time
        if elapsed < self.request_delay_seconds:
            time.sleep(self.request_delay_seconds - elapsed)

        url = f"https://jisho.org/api/v1/search/words?keyword={quote(word)}"
        req = Request(url, headers={"User-Agent": "jp-anki-builder/0.1"})
        try:
            self._last_request_time = time.monotonic()
            with urlopen(req, timeout=self.timeout_seconds) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except (OSError, json.JSONDecodeError, TimeoutError, ValueError) as exc:
            logger.warning("jisho lookup failed for %r: %s", word, exc)
            return None

        data = payload.get("data", [])
        if not data:
            return None

        first = data[0]
        if exact_match:
            first = None
            for item in data:
                for jp in item.get("japanese", []):
                    if jp.get("word") == word:
                        first = item
                        break
                if first is not None:
                    break
            if first is None:
                return None
        japanese = first.get("japanese", [])
        reading = ""
        if japanese:
            reading = japanese[0].get("reading", "") or ""

        meanings: list[str] = []
        for sense in first.get("senses", []):
            for definition in sense.get("english_definitions", []):
                if definition not in meanings:
                    meanings.append(definition)

        if not reading and not meanings:
            return None

        logger.debug("jisho hit: %s -> %s", word, reading)
        return {"reading": reading, "meanings": meanings}


def build_offline_dictionary(base_dir: str = "data"):
    """Factory: returns SQLite dictionary if available, else JSON."""
    sqlite_path = Path(base_dir) / "dictionaries" / "offline.db"
    json_path = Path(base_dir) / "dictionaries" / "offline.json"
    if sqlite_path.exists():
        logger.debug("using SQLite offline dictionary: %s", sqlite_path)
        return OfflineSqliteDictionary(sqlite_path)
    logger.debug("using JSON offline dictionary: %s", json_path)
    return OfflineJsonDictionary(json_path)


def build_online_dictionary(mode: str):
    """Factory for online dictionary providers."""
    if mode == "off":
        return NullOnlineDictionary()
    if mode == "jisho":
        return JishoOnlineDictionary()
    raise ValueError(f"unsupported online dictionary mode: {mode!r}. Use: off or jisho.")


class WordExistsCache:
    """Caches word existence checks across pipeline stages.

    Can be persisted to a JSON file so the build stage reuses
    lookups performed during scan.
    """

    def __init__(self, offline, online=None):
        self._offline = offline
        self._online = online or NullOnlineDictionary()
        self._cache: dict[str, bool] = {}

    def word_exists(self, word: str) -> bool:
        if word in self._cache:
            return self._cache[word]
        hit = self._offline.lookup(word, exact_match=True) is not None
        if not hit:
            hit = self._online.lookup(word, exact_match=True) is not None
        self._cache[word] = hit
        return hit

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(self._cache, ensure_ascii=False),
            encoding="utf-8",
        )
        logger.debug("saved word_exists cache (%d entries) to %s", len(self._cache), path)

    def load(self, path: Path) -> None:
        if not path.exists():
            return
        data = json.loads(path.read_text(encoding="utf-8-sig"))
        self._cache.update(data)
        logger.debug("loaded word_exists cache (%d entries) from %s", len(self._cache), path)
