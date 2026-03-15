from __future__ import annotations

"""Tests for Phase 2 CLI options (Task 2.06)."""

import io
import json
import zipfile
from pathlib import Path

import pytest
from PIL import Image
from typer.testing import CliRunner

from jp_anki_builder.cli import app


def _make_cbz(path: Path, n_pages: int = 2) -> None:
    with zipfile.ZipFile(path, "w") as zf:
        for i in range(n_pages):
            buf = io.BytesIO()
            Image.new("RGB", (10, 10)).save(buf, format="PNG")
            zf.writestr(f"page_{i+1:02d}.png", buf.getvalue())


class TestScanHelpText:
    """--help output describes Phase 2 capabilities."""

    def test_scan_help_mentions_cbz(self):
        result = CliRunner().invoke(app, ["scan", "--help"])
        assert result.exit_code == 0
        assert "cbz" in result.output.lower() or "CBZ" in result.output

    def test_scan_help_mentions_pdf(self):
        result = CliRunner().invoke(app, ["scan", "--help"])
        assert result.exit_code == 0
        assert "pdf" in result.output.lower() or "PDF" in result.output

    def test_scan_help_mentions_detector_mode(self):
        result = CliRunner().invoke(app, ["scan", "--help"])
        assert result.exit_code == 0
        assert "detector" in result.output.lower()

    def test_run_help_mentions_detector_mode(self):
        result = CliRunner().invoke(app, ["run", "--help"])
        assert result.exit_code == 0
        assert "detector" in result.output.lower()


class TestScanAcceptsCbzInput:
    """scan command accepts CBZ file path via --images."""

    def test_scan_with_cbz_succeeds(self, tmp_path: Path, monkeypatch):
        from jp_anki_builder import scan as scan_module
        from jp_anki_builder.normalization import NormalizedCandidate

        cbz = tmp_path / "manga.cbz"
        _make_cbz(cbz)

        class FakeProvider:
            def extract_text(self, p: Path) -> str:
                return "勇者"

        class FakeNorm:
            method_name = "rule_based"
            def normalize_text(self, text, word_exists=None):
                return []

        monkeypatch.setattr(scan_module, "build_ocr_provider", lambda mode, **kw: FakeProvider())
        monkeypatch.setattr(scan_module, "get_default_normalizer", lambda: FakeNorm())

        result = CliRunner().invoke(app, [
            "scan",
            "--images", str(cbz),
            "--source", "manga-a",
            "--run-id", "ch01",
            "--data-dir", str(tmp_path / "data"),
            "--ocr-mode", "sidecar",
        ])

        assert result.exit_code == 0, result.output
        assert "[SCAN]" in result.output

    def test_scan_with_cbz_and_detector_mode_none(self, tmp_path: Path, monkeypatch):
        from jp_anki_builder import scan as scan_module

        cbz = tmp_path / "manga.cbz"
        _make_cbz(cbz)

        class FakeProvider:
            def extract_text(self, p: Path) -> str:
                return ""

        class FakeNorm:
            method_name = "rule_based"
            def normalize_text(self, text, word_exists=None):
                return []

        monkeypatch.setattr(scan_module, "build_ocr_provider", lambda mode, **kw: FakeProvider())
        monkeypatch.setattr(scan_module, "get_default_normalizer", lambda: FakeNorm())

        result = CliRunner().invoke(app, [
            "scan",
            "--images", str(cbz),
            "--source", "manga-a",
            "--run-id", "ch01",
            "--data-dir", str(tmp_path / "data"),
            "--ocr-mode", "sidecar",
            "--detector-mode", "none",
        ])

        assert result.exit_code == 0, result.output


class TestConfigSetDetectorMode:
    """config set detector_mode writes to project config and is read back."""

    def test_config_set_detector_mode_persists(self, tmp_path: Path):
        result = CliRunner().invoke(app, [
            "config", "set", "detector_mode", "paddleocr",
            "--data-dir", str(tmp_path),
        ])
        assert result.exit_code == 0, result.output

        cfg_file = tmp_path / ".jp-anki.json"
        assert cfg_file.exists()
        data = json.loads(cfg_file.read_text())
        assert data["detector_mode"] == "paddleocr"

    def test_config_show_displays_detector_mode(self, tmp_path: Path):
        CliRunner().invoke(app, [
            "config", "set", "detector_mode", "none",
            "--data-dir", str(tmp_path),
        ])
        result = CliRunner().invoke(app, [
            "config", "show",
            "--data-dir", str(tmp_path),
        ])
        assert result.exit_code == 0, result.output
        assert "detector_mode" in result.output


class TestDefaultDetectorModeIsNone:
    """When detector_mode is not set, screenshots workflow is unaffected."""

    def test_scan_without_detector_mode_flag_uses_none_default(self, tmp_path: Path):
        """Screenshot-mode scan works unchanged when --detector-mode is not given."""
        images_dir = tmp_path / "images"
        images_dir.mkdir()
        img = images_dir / "panel.png"
        Image.new("RGB", (10, 10)).save(str(img))
        img.with_suffix(".txt").write_text("勇者", encoding="utf-8")

        result = CliRunner().invoke(app, [
            "scan",
            "--images", str(images_dir),
            "--source", "manga-a",
            "--run-id", "ch01",
            "--data-dir", str(tmp_path / "data"),
            "--ocr-mode", "sidecar",
        ])

        assert result.exit_code == 0, result.output
        artifact = tmp_path / "data" / "manga-a" / "ch01" / "scan.json"
        payload = json.loads(artifact.read_text())
        # No "regions" key — screenshot mode, no detector
        assert "regions" not in payload["records"][0]

    def test_config_detector_mode_applied_as_default(self, tmp_path: Path):
        """detector_mode from config file is used when --detector-mode not given."""
        from jp_anki_builder.project_config import load_project_config
        import json as _json

        cfg_file = tmp_path / ".jp-anki.json"
        cfg_file.write_text(_json.dumps({"detector_mode": "none"}), encoding="utf-8")

        defaults = load_project_config(data_dir=str(tmp_path))
        assert defaults.detector_mode == "none"
