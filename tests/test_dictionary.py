from __future__ import annotations

import json
from io import BytesIO

from jp_anki_builder.dictionary import JishoOnlineDictionary


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
                "japanese": [{"word": "足", "reading": "あし"}],
                "senses": [{"english_definitions": ["foot"]}],
            },
            {
                "japanese": [{"word": "足痛い", "reading": "あしいたい"}],
                "senses": [{"english_definitions": ["test meaning"]}],
            },
        ]
    }
    monkeypatch.setattr(dictionary_module, "urlopen", lambda req, timeout=8: _FakeResponse(payload))

    d = JishoOnlineDictionary()
    hit = d.lookup("足痛い", exact_match=True)
    assert hit is not None
    assert hit["reading"] == "あしいたい"
    assert "test meaning" in hit["meanings"]
