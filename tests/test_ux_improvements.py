"""Tests for UX improvements: path inference, config files, resolved defaults."""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from jp_anki_builder.cli import app
from jp_anki_builder.path_inference import infer_source_and_run_id
from jp_anki_builder.project_config import ProjectDefaults, get_config, load_project_config, set_config, unset_config


# --- Path inference ---

def test_infer_from_directory_path(tmp_path: Path):
    d = tmp_path / "Miharu" / "Prologue"
    d.mkdir(parents=True)
    source, run_id = infer_source_and_run_id(str(d))
    assert source == "Miharu"
    assert run_id == "Prologue"


def test_infer_from_trailing_slash(tmp_path: Path):
    d = tmp_path / "GameX" / "Ch01"
    d.mkdir(parents=True)
    source, run_id = infer_source_and_run_id(str(d) + "/")
    assert source == "GameX"
    assert run_id == "Ch01"


def test_infer_from_single_file(tmp_path: Path):
    d = tmp_path / "Source" / "Run"
    d.mkdir(parents=True)
    f = d / "shot.png"
    f.write_bytes(b"x")
    source, run_id = infer_source_and_run_id(str(f))
    assert source == "Source"
    assert run_id == "Run"


# --- Project config ---

def test_load_project_config_from_file(tmp_path: Path):
    cfg_path = tmp_path / ".jp-anki.json"
    cfg_path.write_text(json.dumps({
        "ocr_mode": "manga-ocr",
        "online_dict": "jisho",
    }), encoding="utf-8")

    cfg = load_project_config(data_dir=str(tmp_path))
    assert cfg.ocr_mode == "manga-ocr"
    assert cfg.online_dict == "jisho"
    assert cfg.ocr_language is None  # not set in config


def test_source_config_overrides_project(tmp_path: Path):
    # Project-level
    (tmp_path / ".jp-anki.json").write_text(json.dumps({
        "ocr_mode": "tesseract",
        "online_dict": "off",
    }), encoding="utf-8")

    # Source-level override
    source_dir = tmp_path / "Miharu"
    source_dir.mkdir()
    (source_dir / ".jp-anki.json").write_text(json.dumps({
        "ocr_mode": "manga-ocr",
    }), encoding="utf-8")

    cfg = load_project_config(data_dir=str(tmp_path), source="Miharu")
    assert cfg.ocr_mode == "manga-ocr"      # source override wins
    assert cfg.online_dict == "off"          # project default preserved


def test_defaults_merge():
    base = ProjectDefaults(ocr_mode="tesseract", online_dict="off")
    override = ProjectDefaults(ocr_mode="manga-ocr")
    merged = base.merge(override)
    assert merged.ocr_mode == "manga-ocr"
    assert merged.online_dict == "off"


# --- Auto-derive in CLI ---

def test_run_auto_derives_source_and_run_id(tmp_path: Path):
    pytest.importorskip("genanki")

    images_dir = tmp_path / "Miharu" / "Prologue"
    images_dir.mkdir(parents=True)
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

    # No --source or --run-id: inferred from images path
    result = CliRunner().invoke(
        app,
        [
            "run",
            "--images", str(images_dir),
            "--data-dir", str(data_dir),
            "--ocr-mode", "sidecar",
        ],
    )

    assert result.exit_code == 0, result.output
    # Check artifacts were created under inferred source/run_id
    assert (data_dir / "Miharu" / "Prologue" / "deck.apkg").exists()


def test_run_uses_config_file_defaults(tmp_path: Path):
    pytest.importorskip("genanki")

    images_dir = tmp_path / "GameX" / "Ch01"
    images_dir.mkdir(parents=True)
    (images_dir / "shot1.png").write_bytes(b"x")
    (images_dir / "shot1.txt").write_text("勇者", encoding="utf-8")

    data_dir = tmp_path / "data"
    dict_dir = data_dir / "dictionaries"
    dict_dir.mkdir(parents=True)
    (dict_dir / "offline.json").write_text(
        json.dumps(
            {"勇者": {"reading": "ゆうしゃ", "meanings": ["hero"]}},
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    # Write project config with sidecar default
    (data_dir / ".jp-anki.json").write_text(json.dumps({
        "ocr_mode": "sidecar",
    }), encoding="utf-8")

    # No --ocr-mode flag: should pick up "sidecar" from config
    result = CliRunner().invoke(
        app,
        [
            "run",
            "--images", str(images_dir),
            "--data-dir", str(data_dir),
        ],
    )

    assert result.exit_code == 0, result.output
    assert (data_dir / "GameX" / "Ch01" / "deck.apkg").exists()


# --- Config CLI commands ---

def test_config_set_get_unset(tmp_path: Path):
    data_dir = str(tmp_path)

    # Set
    updated = set_config("ocr_mode", "manga-ocr", data_dir=data_dir)
    assert updated["ocr_mode"] == "manga-ocr"

    # Get
    cfg = get_config(data_dir=data_dir)
    assert cfg["ocr_mode"] == "manga-ocr"

    # Set another key
    set_config("online_dict", "jisho", data_dir=data_dir)
    cfg = get_config(data_dir=data_dir)
    assert cfg["ocr_mode"] == "manga-ocr"
    assert cfg["online_dict"] == "jisho"

    # Unset
    unset_config("ocr_mode", data_dir=data_dir)
    cfg = get_config(data_dir=data_dir)
    assert "ocr_mode" not in cfg
    assert cfg["online_dict"] == "jisho"


def test_config_set_rejects_invalid_key(tmp_path: Path):
    with pytest.raises(ValueError, match="unknown config key"):
        set_config("bad_key", "value", data_dir=str(tmp_path))


def test_config_set_source_level(tmp_path: Path):
    data_dir = str(tmp_path)
    (tmp_path / "Miharu").mkdir()

    set_config("ocr_mode", "sidecar", data_dir=data_dir, source="Miharu")
    cfg = get_config(data_dir=data_dir, source="Miharu")
    assert cfg["ocr_mode"] == "sidecar"

    # Project level should be empty
    assert get_config(data_dir=data_dir) == {}


def test_config_cli_set_and_show(tmp_path: Path):
    data_dir = str(tmp_path)

    result = CliRunner().invoke(app, [
        "config", "set", "ocr_mode", "manga-ocr",
        "--data-dir", data_dir,
    ])
    assert result.exit_code == 0
    assert "ocr_mode = manga-ocr" in result.output

    result = CliRunner().invoke(app, [
        "config", "show",
        "--data-dir", data_dir,
    ])
    assert result.exit_code == 0
    assert "ocr_mode = manga-ocr" in result.output

    result = CliRunner().invoke(app, [
        "config", "unset", "ocr_mode",
        "--data-dir", data_dir,
    ])
    assert result.exit_code == 0
    assert "removed ocr_mode" in result.output
