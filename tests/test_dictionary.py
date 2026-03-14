from __future__ import annotations

import json
from io import BytesIO
from pathlib import Path

from jp_anki_builder.dictionary import JishoOnlineDictionary, OfflineJsonDictionary


class _FakeResponse:
    def __init__(self, payload: dict):
        self._raw = BytesIO(json.dumps(payload).encode("utf-8"))

    def read(self) -> bytes:
        return self._raw.read()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


def test_jisho_lookup_exact_match(monkeypatch):
    from jp_anki_builder import dictionary as dictionary_module

    payload = {
        "data": [
            {
                "japanese": [{"word": "\u8db3", "reading": "\u3042\u3057"}],
                "senses": [{"english_definitions": ["foot"]}],
            },
            {
                "japanese": [{"word": "\u8db3\u75db\u3044", "reading": "\u3042\u3057\u3044\u305f\u3044"}],
                "senses": [{"english_definitions": ["test meaning"]}],
            },
        ]
    }
    monkeypatch.setattr(dictionary_module, "urlopen", lambda req, timeout=8: _FakeResponse(payload))

    d = JishoOnlineDictionary()
    hit = d.lookup("\u8db3\u75db\u3044", exact_match=True)
    assert hit is not None
    assert hit["reading"] == "\u3042\u3057\u3044\u305f\u3044"
    assert "test meaning" in hit["meanings"]


def test_offline_dictionary_caches_payload_between_lookups(tmp_path: Path, monkeypatch):
    path = tmp_path / "offline.json"
    path.write_text(
        json.dumps({"\u5192\u967a": {"reading": "\u307c\u3046\u3051\u3093", "meanings": ["adventure"]}}, ensure_ascii=False),
        encoding="utf-8",
    )

    read_count = {"n": 0}
    original_read_text = Path.read_text

    def _counting_read_text(self, *args, **kwargs):
        if self == path:
            read_count["n"] += 1
        return original_read_text(self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", _counting_read_text)

    d = OfflineJsonDictionary(path)
    assert d.lookup("\u5192\u967a") is not None
    assert d.lookup("\u52c7\u8005") is None
    assert read_count["n"] == 1
