from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from jp_anki_builder.cli import app


def test_build_exports_apkg_from_review_artifact(tmp_path: Path):
    pytest.importorskip("genanki")

    data_dir = tmp_path / "data"
    run_dir = data_dir / "manga-a" / "run-3"
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
    assert payload["deck_name"] == "manga-a::Vol02::Ch07"
    assert payload["note_count"] == 4


def test_build_uses_online_fallback_when_offline_missing(tmp_path: Path, monkeypatch):
    pytest.importorskip("genanki")

    from jp_anki_builder import build as build_module

    data_dir = tmp_path / "data"
    run_dir = data_dir / "manga-a" / "run-5"
    run_dir.mkdir(parents=True)
    (run_dir / "review.json").write_text(
        json.dumps(
            {
                "source": "manga-a",
                "run_id": "run-5",
                "approved_candidates": ["未登録語"],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    dict_dir = data_dir / "dictionaries"
    dict_dir.mkdir(parents=True)
    (dict_dir / "offline.json").write_text("{}", encoding="utf-8")

    class FakeOnline:
        def lookup(self, word):
            if word == "未登録語":
                return {"reading": "みとうろくご", "meanings": ["unknown term"]}
            return None

    monkeypatch.setattr(build_module, "JishoOnlineDictionary", lambda: FakeOnline())

    result = CliRunner().invoke(
        app,
        [
            "build",
            "--source",
            "manga-a",
            "--run-id",
            "run-5",
            "--data-dir",
            str(data_dir),
            "--online-dict",
            "jisho",
        ],
    )

    assert result.exit_code == 0
    payload = json.loads((run_dir / "build.json").read_text(encoding="utf-8"))
    assert payload["enriched"][0]["reading"] == "みとうろくご"
    assert payload["enriched"][0]["meanings"] == ["unknown term"]


def test_build_skips_words_with_missing_meanings_and_reports_them(tmp_path: Path):
    pytest.importorskip("genanki")

    data_dir = tmp_path / "data"
    run_dir = data_dir / "manga-a" / "run-missing"
    run_dir.mkdir(parents=True)
    (run_dir / "review.json").write_text(
        json.dumps(
            {
                "source": "manga-a",
                "run_id": "run-missing",
                "approved_candidates": ["known_word", "unknown_word"],
            }
        ),
        encoding="utf-8",
    )

    dict_dir = data_dir / "dictionaries"
    dict_dir.mkdir(parents=True)
    (dict_dir / "offline.json").write_text(
        json.dumps(
            {
                "known_word": {"reading": "known_reading", "meanings": ["known meaning"]},
                "unknown_word": {"reading": "", "meanings": []},
            }
        ),
        encoding="utf-8",
    )

    result = CliRunner().invoke(
        app,
        [
            "build",
            "--source",
            "manga-a",
            "--run-id",
            "run-missing",
            "--data-dir",
            str(data_dir),
        ],
    )

    assert result.exit_code == 0
    assert "[BUILD]" in result.stdout
    assert "Missing meaning (1): unknown_word" in result.stdout
    payload = json.loads((run_dir / "build.json").read_text(encoding="utf-8"))
    assert payload["approved_word_count"] == 2
    assert payload["buildable_word_count"] == 1
    assert payload["missing_meaning_count"] == 1
    assert payload["missing_meaning_words"] == ["unknown_word"]
    assert payload["note_count"] == 2


def test_build_fails_when_no_words_have_meanings(tmp_path: Path):
    pytest.importorskip("genanki")

    data_dir = tmp_path / "data"
    run_dir = data_dir / "manga-a" / "run-empty-meanings"
    run_dir.mkdir(parents=True)
    (run_dir / "review.json").write_text(
        json.dumps(
            {
                "source": "manga-a",
                "run_id": "run-empty-meanings",
                "approved_candidates": ["unknown_word"],
            }
        ),
        encoding="utf-8",
    )

    dict_dir = data_dir / "dictionaries"
    dict_dir.mkdir(parents=True)
    (dict_dir / "offline.json").write_text("{}", encoding="utf-8")

    result = CliRunner().invoke(
        app,
        [
            "build",
            "--source",
            "manga-a",
            "--run-id",
            "run-empty-meanings",
            "--data-dir",
            str(data_dir),
        ],
    )

    assert result.exit_code != 0
    assert "[BUILD]" in result.output
    assert "No cards were created for this run." in result.output
    assert "Missing meaning (1): unknown_word" in result.output
    assert "[NEXT] Add meanings to data/dictionaries/offline.json" in result.output

def test_build_rejects_invalid_online_dict_value(tmp_path: Path):
    data_dir = tmp_path / "data"
    run_dir = data_dir / "manga-a" / "run-bad-online"
    run_dir.mkdir(parents=True)
    (run_dir / "review.json").write_text(
        json.dumps(
            {
                "source": "manga-a",
                "run_id": "run-bad-online",
                "approved_candidates": ["\u5192\u967a"],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    result = CliRunner().invoke(
        app,
        [
            "build",
            "--source",
            "manga-a",
            "--run-id",
            "run-bad-online",
            "--data-dir",
            str(data_dir),
            "--online-dict",
            "invalid",
        ],
    )

    assert result.exit_code != 0
    assert "unsupported online dictionary mode" in result.output
