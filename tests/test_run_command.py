from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from jp_anki_builder.cli import app


def test_run_executes_scan_review_build(tmp_path: Path):
    pytest.importorskip("genanki")

    images_dir = tmp_path / "images"
    images_dir.mkdir()
    (images_dir / "shot1.png").write_bytes(b"x")
    (images_dir / "shot1.txt").write_text("冒険 勇者", encoding="utf-8")

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

    result = CliRunner().invoke(
        app,
        [
            "run",
            "--images",
            str(images_dir),
            "--source",
            "manga-a",
            "--run-id",
            "run-4",
            "--data-dir",
            str(data_dir),
            "--ocr-mode",
            "sidecar",
            "--exclude",
            "勇者",
            "--save-excluded-to-known",
            "--volume",
            "01",
            "--chapter",
            "01",
        ],
    )

    assert result.exit_code == 0
    run_dir = data_dir / "manga-a" / "run-4"
    assert (run_dir / "scan.json").exists()
    assert (run_dir / "review.json").exists()
    assert (run_dir / "build.json").exists()
    assert (run_dir / "deck.apkg").exists()


def test_run_fails_when_no_buildable_words_remain(tmp_path: Path):
    pytest.importorskip("genanki")

    images_dir = tmp_path / "images"
    images_dir.mkdir()
    (images_dir / "shot1.png").write_bytes(b"x")
    (images_dir / "shot1.txt").write_text("未知語", encoding="utf-8")

    data_dir = tmp_path / "data"
    dict_dir = data_dir / "dictionaries"
    dict_dir.mkdir(parents=True)
    (dict_dir / "offline.json").write_text("{}", encoding="utf-8")

    result = CliRunner().invoke(
        app,
        [
            "run",
            "--images",
            str(images_dir),
            "--source",
            "manga-a",
            "--run-id",
            "run-no-meanings",
            "--data-dir",
            str(data_dir),
            "--ocr-mode",
            "sidecar",
        ],
    )

    assert result.exit_code != 0
    assert "[SCAN]" in result.output
    assert "[REVIEW]" in result.output
    assert "[BUILD]" in result.output
    assert "No cards were created for this run." in result.output
    assert "Missing meaning (2): 未知, 語" in result.output


def test_run_stops_after_review_when_no_approved_words(tmp_path: Path):
    pytest.importorskip("genanki")

    images_dir = tmp_path / "images"
    images_dir.mkdir()
    (images_dir / "shot1.png").write_bytes(b"x")
    (images_dir / "shot1.txt").write_text("冒険", encoding="utf-8")

    data_dir = tmp_path / "data"
    source_dir = data_dir / "manga-a"
    source_dir.mkdir(parents=True)
    (source_dir / "seen_words.json").write_text(
        json.dumps({"seen_words": ["冒険"]}, ensure_ascii=False),
        encoding="utf-8",
    )
    dict_dir = data_dir / "dictionaries"
    dict_dir.mkdir(parents=True)
    (dict_dir / "offline.json").write_text("{}", encoding="utf-8")

    result = CliRunner().invoke(
        app,
        [
            "run",
            "--images",
            str(images_dir),
            "--source",
            "manga-a",
            "--run-id",
            "run-seen-only",
            "--data-dir",
            str(data_dir),
            "--ocr-mode",
            "sidecar",
        ],
    )

    assert result.exit_code != 0
    assert "[WARN] No approved words remain after review." in result.output
    assert "[WARN] Already seen (1): 冒険" in result.output
    assert not (data_dir / "manga-a" / "run-seen-only" / "deck.apkg").exists()

def test_run_builds_from_normalized_conjugated_input(tmp_path: Path):
    pytest.importorskip("genanki")

    images_dir = tmp_path / "images"
    images_dir.mkdir()
    (images_dir / "shot1.png").write_bytes(b"x")
    (images_dir / "shot1.txt").write_text("\u6b69\u304b\u3055\u308c\u308b", encoding="utf-8")

    data_dir = tmp_path / "data"
    dict_dir = data_dir / "dictionaries"
    dict_dir.mkdir(parents=True)
    (dict_dir / "offline.json").write_text(
        json.dumps(
            {
                "\u6b69\u304f": {"reading": "\u3042\u308b\u304f", "meanings": ["to walk"]},
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    result = CliRunner().invoke(
        app,
        [
            "run",
            "--images",
            str(images_dir),
            "--source",
            "manga-a",
            "--run-id",
            "run-normalized",
            "--data-dir",
            str(data_dir),
            "--ocr-mode",
            "sidecar",
        ],
    )

    assert result.exit_code == 0
    build_payload = json.loads((data_dir / "manga-a" / "run-normalized" / "build.json").read_text(encoding="utf-8"))
    words = [item["word"] for item in build_payload["enriched"]]
    assert "\u6b69\u304f" in words
