from __future__ import annotations

import io
import json
import zipfile

import pytest

from jp_anki_builder.yomichan_dict import YomichanDictionary, YomichanEntry, _flatten_glossary


def _make_yomichan_zip(
    index: dict,
    term_banks: list[list],
    tag_banks: list[list] | None = None,
) -> bytes:
    """Build a minimal Yomichan ZIP in memory and return raw bytes."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("index.json", json.dumps(index, ensure_ascii=False))
        for i, bank in enumerate(term_banks, start=1):
            zf.writestr(f"term_bank_{i}.json", json.dumps(bank, ensure_ascii=False))
        if tag_banks:
            for i, bank in enumerate(tag_banks, start=1):
                zf.writestr(f"tag_bank_{i}.json", json.dumps(bank, ensure_ascii=False))
    return buf.getvalue()


SIMPLE_INDEX = {"title": "TestDict", "format": 3, "revision": "test.1"}

SIMPLE_TERM_BANK = [
    # [expression, reading, definitionTags, rules, score, [glossary...], sequence, termTags]
    ["食べる", "たべる", "v1", "v1", 100, ["to eat", "to consume"], 1, ""],
    ["飲む", "のむ", "v5", "v5m", 90, ["to drink"], 2, ""],
]


class TestFromZip:
    def test_parses_title_and_revision(self, tmp_path):
        zdata = _make_yomichan_zip(SIMPLE_INDEX, [SIMPLE_TERM_BANK])
        p = tmp_path / "dict.zip"
        p.write_bytes(zdata)

        d = YomichanDictionary.from_zip(p)
        assert d.title == "TestDict"
        assert d.revision == "test.1"

    def test_parses_term_entries(self, tmp_path):
        zdata = _make_yomichan_zip(SIMPLE_INDEX, [SIMPLE_TERM_BANK])
        p = tmp_path / "dict.zip"
        p.write_bytes(zdata)

        d = YomichanDictionary.from_zip(p)
        assert "食べる" in d.entries
        assert "飲む" in d.entries

    def test_lookup_returns_entry_fields(self, tmp_path):
        zdata = _make_yomichan_zip(SIMPLE_INDEX, [SIMPLE_TERM_BANK])
        p = tmp_path / "dict.zip"
        p.write_bytes(zdata)

        d = YomichanDictionary.from_zip(p)
        results = d.lookup("食べる")
        assert len(results) == 1
        e = results[0]
        assert e.expression == "食べる"
        assert e.reading == "たべる"
        assert "to eat" in e.meanings
        assert e.rules == "v1"
        assert e.score == 100

    def test_lookup_missing_word_returns_empty(self, tmp_path):
        zdata = _make_yomichan_zip(SIMPLE_INDEX, [SIMPLE_TERM_BANK])
        p = tmp_path / "dict.zip"
        p.write_bytes(zdata)

        d = YomichanDictionary.from_zip(p)
        assert d.lookup("存在しない") == []

    def test_multiple_term_banks_merged(self, tmp_path):
        bank2 = [
            ["走る", "はしる", "", "v5r", 80, ["to run"], 3, ""],
        ]
        zdata = _make_yomichan_zip(SIMPLE_INDEX, [SIMPLE_TERM_BANK, bank2])
        p = tmp_path / "dict.zip"
        p.write_bytes(zdata)

        d = YomichanDictionary.from_zip(p)
        assert "食べる" in d.entries
        assert "走る" in d.entries
        assert len(d.entries) == 3

    def test_tag_banks_parsed(self, tmp_path):
        tag_bank = [
            ["v1", "pos", -3, "Ichidan verb", 0],
        ]
        zdata = _make_yomichan_zip(SIMPLE_INDEX, [SIMPLE_TERM_BANK], tag_banks=[tag_bank])
        p = tmp_path / "dict.zip"
        p.write_bytes(zdata)

        d = YomichanDictionary.from_zip(p)
        e = d.lookup("食べる")[0]
        assert "v1" in e.tags

    def test_invalid_zip_raises_value_error(self, tmp_path):
        p = tmp_path / "bad.zip"
        p.write_bytes(b"not a zip file")

        with pytest.raises(ValueError, match="Cannot open"):
            YomichanDictionary.from_zip(p)

    def test_missing_index_raises_value_error(self, tmp_path):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("term_bank_1.json", "[]")
        p = tmp_path / "no_index.zip"
        p.write_bytes(buf.getvalue())

        with pytest.raises(ValueError, match="Missing index.json"):
            YomichanDictionary.from_zip(p)

    def test_nonexistent_file_raises_value_error(self, tmp_path):
        p = tmp_path / "does_not_exist.zip"
        with pytest.raises(ValueError, match="Cannot open"):
            YomichanDictionary.from_zip(p)


class TestStructuredContent:
    def test_string_glossary_used_directly(self):
        assert _flatten_glossary("to eat") == "to eat"

    def test_text_type_glossary(self):
        g = {"type": "text", "text": "to consume"}
        assert _flatten_glossary(g) == "to consume"

    def test_image_type_glossary_returns_empty(self):
        g = {"type": "image", "path": "/img.png"}
        assert _flatten_glossary(g) == ""

    def test_structured_content_flat_string(self):
        g = {"type": "structured-content", "content": "to eat"}
        assert _flatten_glossary(g) == "to eat"

    def test_structured_content_nested_list(self):
        g = {
            "type": "structured-content",
            "content": [
                {"tag": "span", "content": "to eat"},
                {"tag": "span", "content": "to consume"},
            ],
        }
        result = _flatten_glossary(g)
        assert "to eat" in result
        assert "to consume" in result

    def test_structured_content_deeply_nested(self):
        g = {
            "type": "structured-content",
            "content": {
                "tag": "div",
                "content": [
                    {"tag": "ul", "content": [
                        {"tag": "li", "content": "definition one"},
                        {"tag": "li", "content": "definition two"},
                    ]},
                ],
            },
        }
        result = _flatten_glossary(g)
        assert "definition one" in result
        assert "definition two" in result

    def test_structured_content_in_full_parse(self, tmp_path):
        structured_glossary = {
            "type": "structured-content",
            "content": [
                {"tag": "span", "content": "to eat"},
                {"tag": "span", "content": "(food)"},
            ],
        }
        bank = [
            ["食べる", "たべる", "", "v1", 100, [structured_glossary], 1, ""],
        ]
        zdata = _make_yomichan_zip(SIMPLE_INDEX, [bank])
        p = tmp_path / "dict.zip"
        p.write_bytes(zdata)

        d = YomichanDictionary.from_zip(p)
        e = d.lookup("食べる")[0]
        assert len(e.meanings) == 1
        assert "to eat" in e.meanings[0]
