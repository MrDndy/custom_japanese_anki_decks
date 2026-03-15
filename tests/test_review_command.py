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


def test_confidence_metadata_propagates_to_review_json(tmp_path: Path):
    import tempfile, shutil
    tmp = tempfile.mkdtemp()
    try:
        from pathlib import Path as P
        from jp_anki_builder.review import prepare_review, run_review

        run_dir = P(tmp) / "manga-a" / "run-conf"
        run_dir.mkdir(parents=True)

        # Scan artifact with normalized_candidates including confidence data
        scan_payload = {
            "source": "manga-a",
            "run_id": "run-conf",
            "candidates": ["勇者", "走る", "謎"],
            "records": [
                {
                    "image": "img1.png",
                    "text": "勇者は走る",
                    "candidates": ["勇者", "走る"],
                    "normalized_candidates": [
                        {"surface": "勇者", "lemma": "勇者", "method": "sudachi_nlp",
                         "confidence": 0.97, "reason": "dictionary", "surface_chain": None},
                        {"surface": "走っ", "lemma": "走る", "method": "sudachi_nlp",
                         "confidence": 0.65, "reason": "surface_fallback", "surface_chain": None},
                    ],
                    "alternate_texts": [], "surface_tokens": [],
                },
                {
                    "image": "img2.png",
                    "text": "謎",
                    "candidates": ["謎"],
                    "normalized_candidates": [
                        {"surface": "謎", "lemma": "謎", "method": "sudachi_nlp",
                         "confidence": 0.85, "reason": "low_freq", "surface_chain": None},
                    ],
                    "alternate_texts": [], "surface_tokens": [],
                },
            ],
        }
        (run_dir / "scan.json").write_text(
            json.dumps(scan_payload, ensure_ascii=False), encoding="utf-8"
        )

        summary = run_review(source="manga-a", run_id="run-conf", base_dir=tmp)
        review = json.loads((run_dir / "review.json").read_text(encoding="utf-8"))

        # approved_candidates unchanged (still a list of strings)
        assert review["approved_candidates"] == ["勇者", "走る", "謎"]

        # confidence metadata present for words that have it
        meta = review["approved_candidates_meta"]
        assert meta["勇者"]["confidence"] == 0.97
        assert meta["勇者"]["reason"] == "dictionary"
        assert meta["走る"]["confidence"] == 0.65
        assert meta["走る"]["reason"] == "surface_fallback"

        # low-confidence words flagged (< 0.90 or reason == surface_fallback)
        low = review["low_confidence_candidates"]
        assert "走る" in low   # surface_fallback
        assert "謎" in low     # confidence 0.85 < 0.90
        assert "勇者" not in low  # confidence 0.97, dictionary → fine

        # summary also exposes low_confidence_candidates
        assert "走る" in summary.low_confidence_candidates
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
