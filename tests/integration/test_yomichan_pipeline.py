"""Integration test: Yomichan dictionary install -> lookup -> batch pipeline."""
from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path

import pytest


def _make_yomichan_zip(entries: list[list]) -> bytes:
    """Build a minimal Yomichan dictionary ZIP in memory."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("index.json", json.dumps({
            "title": "Test Dict",
            "format": 3,
            "revision": "1.0",
        }))
        zf.writestr("term_bank_1.json", json.dumps(entries))
    return buf.getvalue()


@pytest.fixture()
def yomichan_env(tmp_path: Path):
    """Set up data directory with JMdict + Yomichan dictionary."""
    data_dir = tmp_path / "data"
    dict_dir = data_dir / "dictionaries"
    dict_dir.mkdir(parents=True)

    # Minimal JMdict offline.json (missing the test word deliberately)
    jmdict = {
        "食べる": {"reading": "たべる", "meanings": ["to eat"]},
    }
    (dict_dir / "offline.json").write_text(
        json.dumps(jmdict, ensure_ascii=False), encoding="utf-8"
    )

    # Yomichan dict with a word NOT in JMdict
    yomichan_dir = dict_dir / "yomichan"
    yomichan_dir.mkdir()
    entries = [
        ["竜巻", "たつまき", "", "", 100, ["tornado; whirlwind"], 1, ""],
        ["雷鳴", "らいめい", "", "", 80, ["thunder; thunderclap"], 2, ""],
    ]
    zip_data = _make_yomichan_zip(entries)
    (yomichan_dir / "test_dict.zip").write_bytes(zip_data)

    return data_dir


class TestYomichanFallbackInPipeline:
    """Verify that words found only in Yomichan dicts are discovered during lookup."""

    def test_composite_finds_yomichan_word(self, yomichan_env: Path):
        from jp_anki_builder.dictionary import build_offline_dictionary
        d = build_offline_dictionary(base_dir=str(yomichan_env))

        # JMdict hit
        result = d.lookup("食べる", exact_match=True)
        assert result is not None
        assert "to eat" in result["meanings"]

        # Yomichan fallback hit
        result = d.lookup("竜巻", exact_match=True)
        assert result is not None
        assert any("tornado" in m for m in result["meanings"])

    def test_word_exists_cache_includes_yomichan(self, yomichan_env: Path):
        from jp_anki_builder.dictionary import WordExistsCache, build_offline_dictionary
        offline = build_offline_dictionary(base_dir=str(yomichan_env))
        cache = WordExistsCache(offline)

        assert cache.word_exists("食べる") is True  # JMdict
        assert cache.word_exists("竜巻") is True     # Yomichan
        assert cache.word_exists("zzz_nonexistent") is False

    def test_jmdict_miss_yomichan_hit_during_normalization(self, yomichan_env: Path):
        """Ensure normalization uses Yomichan when JMdict doesn't have the word."""
        from jp_anki_builder.dictionary import WordExistsCache, build_offline_dictionary
        from jp_anki_builder.normalization import _choose_best_candidate

        offline = build_offline_dictionary(base_dir=str(yomichan_env))
        cache = WordExistsCache(offline)

        # "竜巻" is only in Yomichan — should validate
        lemma, confidence, reason = _choose_best_candidate(
            "竜巻", "竜巻", cache.word_exists
        )
        assert lemma == "竜巻"
        assert confidence == 0.99
        assert reason == "dictionary_validated"


class TestInstallYomichanDict:
    """Verify the install workflow copies and validates."""

    def test_install_copies_zip(self, tmp_path: Path):
        """Install via CLI command copies ZIP to yomichan directory."""
        import shutil

        from jp_anki_builder.yomichan_dict import YomichanDictionary

        data_dir = tmp_path / "data"
        yomichan_dir = data_dir / "dictionaries" / "yomichan"
        yomichan_dir.mkdir(parents=True)

        # Create a valid ZIP in a source location
        src = tmp_path / "source.zip"
        entries = [["猫", "ねこ", "", "", 100, ["cat"], 1, ""]]
        src.write_bytes(_make_yomichan_zip(entries))

        # Replicate the install logic from cli.py
        d = YomichanDictionary.from_zip(src)
        assert d.title == "Test Dict"

        dest = yomichan_dir / src.name
        shutil.copy2(src, dest)
        assert dest.exists()
        assert dest.parent == yomichan_dir

    def test_install_invalid_zip_raises(self, tmp_path: Path):
        from jp_anki_builder.yomichan_dict import YomichanDictionary

        bad_zip = tmp_path / "bad.zip"
        bad_zip.write_text("not a zip", encoding="utf-8")

        with pytest.raises((ValueError, zipfile.BadZipFile)):
            YomichanDictionary.from_zip(bad_zip)
