from __future__ import annotations

import json
from urllib.parse import quote
from urllib.request import Request, urlopen
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


@dataclass
class JishoOnlineDictionary:
    timeout_seconds: int = 8

    def lookup(self, word: str):
        url = f"https://jisho.org/api/v1/search/words?keyword={quote(word)}"
        req = Request(url, headers={"User-Agent": "jp-anki-builder/0.1"})
        try:
            with urlopen(req, timeout=self.timeout_seconds) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except Exception:
            return None

        data = payload.get("data", [])
        if not data:
            return None

        first = data[0]
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

        return {"reading": reading, "meanings": meanings}
