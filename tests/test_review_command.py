from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from jp_anki_builder.cli import app


def test_review_filters_known_words_and_updates_source_seen(tmp_path: Path):
    data_dir = tmp_path / "data"
    run_dir = data_dir / "manga-a" / "run-1"
    run_dir.mkdir(parents=True)
    (run_dir / "scan.json").write_text(
        json.dumps(
            {
                "source": "manga-a",
                "run_id": "run-1",
                "candidates": ["勇者", "は", "冒険"],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (data_dir / "manga-a" / "known_words.txt").write_text("勇者\n", encoding="utf-8")

    result = CliRunner().invoke(
        app,
        [
            "review",
            "--source",
            "manga-a",
            "--run-id",
            "run-1",
            "--data-dir",
            str(data_dir),
        ],
    )

    assert result.exit_code == 0
    payload = json.loads((run_dir / "review.json").read_text(encoding="utf-8"))
    assert payload["approved_candidates"] == ["冒険"]

    source_seen = json.loads((data_dir / "manga-a" / "seen_words.json").read_text(encoding="utf-8"))
    assert source_seen["seen_words"] == ["冒険"]


def test_review_can_save_manual_exclusions_to_known_words(tmp_path: Path):
    data_dir = tmp_path / "data"
    run_dir = data_dir / "manga-a" / "run-2"
    run_dir.mkdir(parents=True)
    (run_dir / "scan.json").write_text(
        json.dumps(
            {
                "source": "manga-a",
                "run_id": "run-2",
                "candidates": ["魔法", "剣"],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    result = CliRunner().invoke(
        app,
        [
            "review",
            "--source",
            "manga-a",
            "--run-id",
            "run-2",
            "--data-dir",
            str(data_dir),
            "--exclude",
            "剣",
            "--save-excluded-to-known",
        ],
    )

    assert result.exit_code == 0
    known = (data_dir / "manga-a" / "known_words.txt").read_text(encoding="utf-8")
    assert "剣" in known


def test_review_interactive_exclude_and_save(tmp_path: Path):
    data_dir = tmp_path / "data"
    run_dir = data_dir / "manga-a" / "run-3"
    run_dir.mkdir(parents=True)
    (run_dir / "scan.json").write_text(
        json.dumps(
            {
                "source": "manga-a",
                "run_id": "run-3",
                "candidates": ["勇者", "冒険"],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    result = CliRunner().invoke(
        app,
        [
            "review",
            "--source",
            "manga-a",
            "--run-id",
            "run-3",
            "--data-dir",
            str(data_dir),
            "--interactive",
        ],
        input="2\ny\n",
    )

    assert result.exit_code == 0
    review_payload = json.loads((run_dir / "review.json").read_text(encoding="utf-8"))
    assert review_payload["approved_candidates"] == ["勇者"]
    known = (data_dir / "manga-a" / "known_words.txt").read_text(encoding="utf-8")
    assert "冒険" in known


def test_review_reports_skipped_words_by_reason_in_cli_output(tmp_path: Path):
    data_dir = tmp_path / "data"
    run_dir = data_dir / "manga-a" / "run-seen"
    run_dir.mkdir(parents=True)
    (run_dir / "scan.json").write_text(
        json.dumps(
            {
                "source": "manga-a",
                "run_id": "run-seen",
                "candidates": ["冒険", "冒険", "勇者", "は"],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (data_dir / "manga-a" / "known_words.txt").write_text("勇者\n", encoding="utf-8")
    source_dir = data_dir / "manga-a"
    source_dir.mkdir(parents=True, exist_ok=True)
    (source_dir / "seen_words.json").write_text(
        json.dumps({"seen_words": ["冒険"]}, ensure_ascii=False),
        encoding="utf-8",
    )

    result = CliRunner().invoke(
        app,
        [
            "review",
            "--source",
            "manga-a",
            "--run-id",
            "run-seen",
            "--data-dir",
            str(data_dir),
        ],
    )

    assert result.exit_code == 0
    assert "[REVIEW]" in result.stdout
    assert "[WARN] Known (1): 勇者" in result.stdout
    assert "[WARN] Particle (1): は" in result.stdout
    assert "[WARN] Already seen (1): 冒険" in result.stdout
