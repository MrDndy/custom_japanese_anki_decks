"""Tests for medium-impact improvements: rate limiting, shared cache,
incremental scan, dry-run, and SQLite dictionary."""
from __future__ import annotations

import json
import time
from pathlib import Path

import pytest
from typer.testing import CliRunner

from jp_anki_builder.cli import app
from jp_anki_builder.dictionary import (
    JishoOnlineDictionary,
    OfflineJsonDictionary,
    OfflineSqliteDictionary,
    WordExistsCache,
    build_offline_dictionary,
)


# --- Rate-limit Jisho ---

def test_jisho_rate_limits_between_requests(monkeypatch):
    from jp_anki_builder import dictionary as dict_mod

    call_times: list[float] = []
    orig_urlopen = dict_mod.urlopen

    def tracking_urlopen(req, timeout=8):
        call_times.append(time.monotonic())
        raise OSError("no network in test")

    monkeypatch.setattr(dict_mod, "urlopen", tracking_urlopen)

    d = JishoOnlineDictionary(request_delay_seconds=0.15)
    d.lookup("a")
    d.lookup("b")

    assert len(call_times) == 2
    gap = call_times[1] - call_times[0]
    assert gap >= 0.1, f"expected >= 0.1s gap, got {gap:.3f}s"


# --- Shared word_exists cache ---

def test_word_exists_cache_save_load(tmp_path: Path):
    offline_path = tmp_path / "offline.json"
    offline_path.write_text(
        json.dumps({"冒険": {"reading": "ぼうけん", "meanings": ["adventure"]}}, ensure_ascii=False),
        encoding="utf-8",
    )
    offline = OfflineJsonDictionary(offline_path)
    cache = WordExistsCache(offline)
    assert cache.word_exists("冒険") is True
    assert cache.word_exists("未知語") is False

    cache_path = tmp_path / "cache.json"
    cache.save(cache_path)

    # Load into fresh cache
    cache2 = WordExistsCache(offline)
    cache2.load(cache_path)
    # Should use cached values without re-querying
    assert cache2.word_exists("冒険") is True
    assert cache2.word_exists("未知語") is False


# --- Incremental / resumable scan ---

def test_scan_resume_skips_completed_images(tmp_path: Path):
    images_dir = tmp_path / "images"
    images_dir.mkdir()
    (images_dir / "a.png").write_bytes(b"x")
    (images_dir / "a.txt").write_text("冒険", encoding="utf-8")
    (images_dir / "b.png").write_bytes(b"x")
    (images_dir / "b.txt").write_text("勇者", encoding="utf-8")

    data_dir = tmp_path / "data"
    dict_dir = data_dir / "dictionaries"
    dict_dir.mkdir(parents=True)
    (dict_dir / "offline.json").write_text(
        json.dumps(
            {
                "冒険": {"reading": "ぼうけん", "meanings": ["adventure"]},
                "勇者": {"reading": "ゆうしゃ", "meanings": ["hero"]},
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    # First scan: only process image a
    result1 = CliRunner().invoke(
        app,
        [
            "scan",
            "--images", str(images_dir / "a.png"),
            "--source", "test",
            "--run-id", "r1",
            "--data-dir", str(data_dir),
            "--ocr-mode", "sidecar",
        ],
    )
    assert result1.exit_code == 0

    # Manually check scan.json has 1 record
    scan_path = data_dir / "test" / "r1" / "scan.json"
    scan_data = json.loads(scan_path.read_text(encoding="utf-8"))
    assert len(scan_data["records"]) == 1

    # Now scan entire dir with resume - a.png should be skipped
    result2 = CliRunner().invoke(
        app,
        [
            "scan",
            "--images", str(images_dir),
            "--source", "test",
            "--run-id", "r1",
            "--data-dir", str(data_dir),
            "--ocr-mode", "sidecar",
            "--resume",
        ],
    )
    assert result2.exit_code == 0
    assert "Resumed" in result2.output

    scan_data2 = json.loads(scan_path.read_text(encoding="utf-8"))
    assert len(scan_data2["records"]) == 2


# --- Dry-run ---

def test_run_dry_run_does_not_create_deck(tmp_path: Path):
    images_dir = tmp_path / "images"
    images_dir.mkdir()
    (images_dir / "shot1.png").write_bytes(b"x")
    (images_dir / "shot1.txt").write_text("冒険", encoding="utf-8")

    data_dir = tmp_path / "data"
    dict_dir = data_dir / "dictionaries"
    dict_dir.mkdir(parents=True)
    (dict_dir / "offline.json").write_text(
        json.dumps(
            {"冒険": {"reading": "ぼうけん", "meanings": ["adventure"]}},
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    result = CliRunner().invoke(
        app,
        [
            "run",
            "--images", str(images_dir),
            "--source", "manga-a",
            "--run-id", "dry-1",
            "--data-dir", str(data_dir),
            "--ocr-mode", "sidecar",
            "--dry-run",
        ],
    )

    assert result.exit_code == 0
    assert "dry-run" in result.output
    assert "No artifacts written" in result.output
    # scan.json is written (needed for review plan), but no review/build/deck
    assert not (data_dir / "manga-a" / "dry-1" / "review.json").exists()
    assert not (data_dir / "manga-a" / "dry-1" / "deck.apkg").exists()


# --- SQLite dictionary ---

def test_sqlite_dictionary_lookup(tmp_path: Path):
    json_path = tmp_path / "offline.json"
    json_path.write_text(
        json.dumps(
            {
                "冒険": {"reading": "ぼうけん", "meanings": ["adventure"]},
                "勇者": {"reading": "ゆうしゃ", "meanings": ["hero", "brave"]},
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    sqlite_path = tmp_path / "offline.db"
    count = OfflineSqliteDictionary.create_from_json(json_path, sqlite_path)
    assert count == 2

    d = OfflineSqliteDictionary(sqlite_path)
    hit = d.lookup("冒険")
    assert hit is not None
    assert hit["reading"] == "ぼうけん"
    assert hit["meanings"] == ["adventure"]

    assert d.lookup("存在しない") is None
    d.close()


def test_build_offline_dictionary_prefers_sqlite(tmp_path: Path):
    dict_dir = tmp_path / "dictionaries"
    dict_dir.mkdir()

    json_path = dict_dir / "offline.json"
    json_path.write_text(
        json.dumps({"word": {"reading": "r", "meanings": ["m"]}}, ensure_ascii=False),
        encoding="utf-8",
    )

    # Without sqlite, returns JSON dict
    d1 = build_offline_dictionary(str(tmp_path))
    assert isinstance(d1, OfflineJsonDictionary)

    # Create sqlite
    sqlite_path = dict_dir / "offline.db"
    OfflineSqliteDictionary.create_from_json(json_path, sqlite_path)

    # Now returns sqlite dict
    d2 = build_offline_dictionary(str(tmp_path))
    assert isinstance(d2, OfflineSqliteDictionary)
    assert d2.lookup("word") is not None
    d2.close()
