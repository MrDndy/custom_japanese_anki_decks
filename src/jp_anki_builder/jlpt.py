from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

JLPT_DATA_FILENAME = "jlpt_levels.json"


@dataclass
class JlptLookup:
    """Looks up JLPT level for a given word.

    The data file maps words to their JLPT level (1-5, where 1 is hardest).
    """

    path: Path
    _cache: dict[str, int] | None = None

    def level(self, word: str) -> int | None:
        data = self._load()
        if data is None:
            return None
        return data.get(word)

    def level_tag(self, word: str) -> str:
        lvl = self.level(word)
        if lvl is None:
            return ""
        return f"N{lvl}"

    def _load(self) -> dict[str, int] | None:
        if self._cache is not None:
            return self._cache
        if not self.path.exists():
            logger.debug("JLPT data file not found: %s", self.path)
            self._cache = {}
            return self._cache
        logger.debug("loading JLPT data from %s", self.path)
        raw = json.loads(self.path.read_text(encoding="utf-8-sig"))
        self._cache = {word: int(level) for word, level in raw.items()}
        return self._cache


def build_jlpt_lookup(base_dir: str = "data") -> JlptLookup:
    return JlptLookup(path=Path(base_dir) / "dictionaries" / JLPT_DATA_FILENAME)
