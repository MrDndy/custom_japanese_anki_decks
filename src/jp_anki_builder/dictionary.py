from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass
class OfflineJsonDictionary:
    path: Path

    def lookup(self, word: str):
        if not self.path.exists():
            return None
        payload = json.loads(self.path.read_text(encoding="utf-8-sig"))
        return payload.get(word)


@dataclass
class NullOnlineDictionary:
    def lookup(self, word: str):
        return None
