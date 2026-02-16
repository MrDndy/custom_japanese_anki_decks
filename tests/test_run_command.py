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
    run_dir = data_dir / "runs" / "run-4"
    assert (run_dir / "scan.json").exists()
    assert (run_dir / "review.json").exists()
    assert (run_dir / "build.json").exists()
    assert (run_dir / "deck.apkg").exists()
