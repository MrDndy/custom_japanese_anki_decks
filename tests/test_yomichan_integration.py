from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path

import pytest
from typer.testing import CliRunner

from jp_anki_builder.cli import app
from jp_anki_builder.dictionary import (
    CompositeDictionary,
    NullOnlineDictionary,
    OfflineJsonDictionary,
    WordExistsCache,
    YomichanDictionaryProvider,
    build_offline_dictionary,
)


def _make_yomichan_zip(title: str, entries: list[list]) -> bytes:
    index = {"title": title, "format": 3, "revision": "test.1"}
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("index.json", json.dumps(index))
        zf.writestr("term_bank_1.json", json.dumps(entries))
    return buf.getvalue()


TABERU_ENTRY = ["食べる", "たべる", "", "v1", 100, ["to eat"], 1, ""]
NOMIMONO_ENTRY = ["飲み物", "のみもの", "", "", 80, ["beverage", "drink"], 2, ""]


class TestYomichanDictionaryProvider:
    def test_lookup_hits_loaded_dict(self, tmp_path):
        ydir = tmp_path / "yomichan"
        ydir.mkdir()
        (ydir / "test.zip").write_bytes(_make_yomichan_zip("TestDict", [TABERU_ENTRY]))

        provider = YomichanDictionaryProvider(dict_dir=ydir)
        result = provider.lookup("食べる")
        assert result is not None
        assert result["reading"] == "たべる"
        assert "to eat" in result["meanings"]

    def test_lookup_miss_returns_none(self, tmp_path):
        ydir = tmp_path / "yomichan"
        ydir.mkdir()
        (ydir / "test.zip").write_bytes(_make_yomichan_zip("TestDict", [TABERU_ENTRY]))

        provider = YomichanDictionaryProvider(dict_dir=ydir)
        assert provider.lookup("存在しない") is None

    def test_empty_directory_returns_none(self, tmp_path):
        ydir = tmp_path / "yomichan"
        ydir.mkdir()
        provider = YomichanDictionaryProvider(dict_dir=ydir)
        assert provider.lookup("食べる") is None

    def test_missing_directory_returns_none(self, tmp_path):
        ydir = tmp_path / "yomichan_does_not_exist"
        provider = YomichanDictionaryProvider(dict_dir=ydir)
        assert provider.lookup("食べる") is None

    def test_invalid_zip_skipped_gracefully(self, tmp_path):
        ydir = tmp_path / "yomichan"
        ydir.mkdir()
        (ydir / "bad.zip").write_bytes(b"not a zip")
        (ydir / "good.zip").write_bytes(_make_yomichan_zip("Good", [TABERU_ENTRY]))

        provider = YomichanDictionaryProvider(dict_dir=ydir)
        result = provider.lookup("食べる")
        assert result is not None

    def test_multiple_dicts_searched(self, tmp_path):
        ydir = tmp_path / "yomichan"
        ydir.mkdir()
        (ydir / "dict1.zip").write_bytes(_make_yomichan_zip("Dict1", [TABERU_ENTRY]))
        (ydir / "dict2.zip").write_bytes(_make_yomichan_zip("Dict2", [NOMIMONO_ENTRY]))

        provider = YomichanDictionaryProvider(dict_dir=ydir)
        assert provider.lookup("食べる") is not None
        assert provider.lookup("飲み物") is not None


class TestCompositeDictionary:
    def test_returns_first_hit(self, tmp_path):
        json_path = tmp_path / "offline.json"
        json_path.write_text(
            json.dumps({"走る": {"reading": "はしる", "meanings": ["to run"]}}),
            encoding="utf-8",
        )
        jmdict = OfflineJsonDictionary(json_path)

        ydir = tmp_path / "yomichan"
        ydir.mkdir()
        (ydir / "dict.zip").write_bytes(_make_yomichan_zip("Y", [TABERU_ENTRY]))
        yomichan = YomichanDictionaryProvider(dict_dir=ydir)

        composite = CompositeDictionary(providers=[jmdict, yomichan])

        # JMdict hit
        run_result = composite.lookup("走る")
        assert run_result is not None
        assert run_result["reading"] == "はしる"

        # Yomichan fallback (not in JMdict)
        eat_result = composite.lookup("食べる")
        assert eat_result is not None
        assert eat_result["reading"] == "たべる"

    def test_miss_returns_none(self, tmp_path):
        json_path = tmp_path / "offline.json"
        json_path.write_text("{}", encoding="utf-8")
        jmdict = OfflineJsonDictionary(json_path)

        ydir = tmp_path / "yomichan"
        ydir.mkdir()
        composite = CompositeDictionary(providers=[jmdict, YomichanDictionaryProvider(ydir)])
        assert composite.lookup("存在しない") is None


class TestBuildOfflineDictionaryComposite:
    def test_returns_composite(self, tmp_path):
        dict_dir = tmp_path / "dictionaries"
        dict_dir.mkdir()
        (dict_dir / "offline.json").write_text(
            json.dumps({"走る": {"reading": "はしる", "meanings": ["to run"]}}),
            encoding="utf-8",
        )
        result = build_offline_dictionary(str(tmp_path))
        assert isinstance(result, CompositeDictionary)

    def test_jmdict_hit(self, tmp_path):
        dict_dir = tmp_path / "dictionaries"
        dict_dir.mkdir()
        (dict_dir / "offline.json").write_text(
            json.dumps({"走る": {"reading": "はしる", "meanings": ["to run"]}}),
            encoding="utf-8",
        )
        composite = build_offline_dictionary(str(tmp_path))
        hit = composite.lookup("走る")
        assert hit is not None
        assert hit["reading"] == "はしる"

    def test_yomichan_fallback_when_jmdict_misses(self, tmp_path):
        dict_dir = tmp_path / "dictionaries"
        dict_dir.mkdir()
        (dict_dir / "offline.json").write_text("{}", encoding="utf-8")
        ydir = dict_dir / "yomichan"
        ydir.mkdir()
        (ydir / "dict.zip").write_bytes(_make_yomichan_zip("Y", [TABERU_ENTRY]))

        composite = build_offline_dictionary(str(tmp_path))
        hit = composite.lookup("食べる")
        assert hit is not None
        assert hit["reading"] == "たべる"

    def test_jmdict_only_when_no_yomichan(self, tmp_path):
        dict_dir = tmp_path / "dictionaries"
        dict_dir.mkdir()
        (dict_dir / "offline.json").write_text(
            json.dumps({"走る": {"reading": "はしる", "meanings": ["to run"]}}),
            encoding="utf-8",
        )
        composite = build_offline_dictionary(str(tmp_path))
        assert composite.lookup("走る") is not None
        assert composite.lookup("食べる") is None


class TestWordExistsCacheWithComposite:
    def test_word_exists_via_yomichan(self, tmp_path):
        dict_dir = tmp_path / "dictionaries"
        dict_dir.mkdir()
        (dict_dir / "offline.json").write_text("{}", encoding="utf-8")
        ydir = dict_dir / "yomichan"
        ydir.mkdir()
        (ydir / "dict.zip").write_bytes(_make_yomichan_zip("Y", [TABERU_ENTRY]))

        composite = build_offline_dictionary(str(tmp_path))
        cache = WordExistsCache(composite, NullOnlineDictionary())
        assert cache.word_exists("食べる") is True
        assert cache.word_exists("存在しない") is False


class TestInstallYomichanDictCLI:
    def test_install_valid_zip(self, tmp_path):
        runner = CliRunner()
        src = tmp_path / "mydict.zip"
        src.write_bytes(_make_yomichan_zip("MyDict", [TABERU_ENTRY]))

        result = runner.invoke(
            app,
            ["install-yomichan-dict", "--file", str(src), "--data-dir", str(tmp_path)],
        )
        assert result.exit_code == 0, result.output
        assert "MyDict" in result.output
        dest = tmp_path / "dictionaries" / "yomichan" / "mydict.zip"
        assert dest.exists()

    def test_install_invalid_zip_exits_nonzero(self, tmp_path):
        runner = CliRunner()
        src = tmp_path / "bad.zip"
        src.write_bytes(b"not a zip")

        result = runner.invoke(
            app,
            ["install-yomichan-dict", "--file", str(src), "--data-dir", str(tmp_path)],
        )
        assert result.exit_code != 0
        assert "Invalid" in result.output

    def test_install_missing_file_exits_nonzero(self, tmp_path):
        runner = CliRunner()
        result = runner.invoke(
            app,
            ["install-yomichan-dict", "--file", str(tmp_path / "no.zip"), "--data-dir", str(tmp_path)],
        )
        assert result.exit_code != 0
        assert "not found" in result.output.lower() or "File not found" in result.output
