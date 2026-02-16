from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from jp_anki_builder.cli import app


def test_build_exports_apkg_from_review_artifact(tmp_path: Path):
    pytest.importorskip("genanki")

    data_dir = tmp_path / "data"
    run_dir = data_dir / "runs" / "run-3"
    run_dir.mkdir(parents=True)
    (run_dir / "review.json").write_text(
        json.dumps(
            {
                "source": "manga-a",
                "run_id": "run-3",
                "approved_candidates": ["冒険", "勇者"],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

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
        encoding="utf-8-sig",
    )

    result = CliRunner().invoke(
        app,
        [
            "build",
            "--source",
            "manga-a",
            "--run-id",
            "run-3",
            "--data-dir",
            str(data_dir),
            "--volume",
            "02",
            "--chapter",
            "07",
        ],
    )

    assert result.exit_code == 0
    apkg = run_dir / "deck.apkg"
    assert apkg.exists()

    payload = json.loads((run_dir / "build.json").read_text(encoding="utf-8"))
    assert payload["deck_name"] == "manga-a::Volume02::Chapter07"
    assert payload["note_count"] == 4
