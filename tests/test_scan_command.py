from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from jp_anki_builder.cli import app


def test_scan_writes_artifact_from_sidecar_ocr(tmp_path: Path):
    images_dir = tmp_path / "images"
    images_dir.mkdir()
    image = images_dir / "panel1.png"
    image.write_bytes(b"fake")
    image.with_suffix(".txt").write_text("冒険に行く 勇者", encoding="utf-8")

    data_dir = tmp_path / "data"

    result = CliRunner().invoke(
        app,
        [
            "scan",
            "--images",
            str(images_dir),
            "--source",
            "manga-a",
            "--run-id",
            "manga-a-ch01",
            "--data-dir",
            str(data_dir),
            "--ocr-mode",
            "sidecar",
        ],
    )

    assert result.exit_code == 0
    artifact = data_dir / "runs" / "manga-a-ch01" / "scan.json"
    assert artifact.exists()

    payload = json.loads(artifact.read_text(encoding="utf-8"))
    assert payload["source"] == "manga-a"
    assert payload["image_count"] == 1
    assert "冒険に行く" in payload["candidates"]
    assert "勇者" in payload["candidates"]


def test_scan_errors_when_no_images_found(tmp_path: Path):
    missing = tmp_path / "missing"

    result = CliRunner().invoke(
        app,
        [
            "scan",
            "--images",
            str(missing),
            "--source",
            "manga-a",
            "--run-id",
            "manga-a-empty",
        ],
    )

    assert result.exit_code != 0
    assert "No image files found" in result.output
