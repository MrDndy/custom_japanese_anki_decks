from __future__ import annotations

"""Tests for Phase 2 scan integrations: format handlers + region detection."""

import io
import json
import zipfile
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from PIL import Image
from typer.testing import CliRunner

from jp_anki_builder.cli import app
from jp_anki_builder.normalization import NormalizedCandidate


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_cbz(path: Path, image_names: list[str]) -> None:
    """Write a minimal CBZ file containing blank PNG images."""
    with zipfile.ZipFile(path, "w") as zf:
        for name in image_names:
            buf = io.BytesIO()
            Image.new("RGB", (10, 10), color=(200, 200, 200)).save(buf, format="PNG")
            zf.writestr(name, buf.getvalue())


class _FakeNormalizer:
    method_name = "rule_based"

    def normalize_text(self, text: str, word_exists=None) -> list[NormalizedCandidate]:
        return []


# ---------------------------------------------------------------------------
# CBZ input: extract_pages called, images processed
# ---------------------------------------------------------------------------

class TestScanWithCbzInput:
    """run_scan accepts a CBZ file and processes its pages."""

    def test_cbz_input_produces_scan_artifact(self, tmp_path: Path, monkeypatch):
        from jp_anki_builder import scan as scan_module

        cbz = tmp_path / "manga.cbz"
        _make_cbz(cbz, ["page_01.png", "page_02.png"])

        # Patch OCR to return a known word so we can check candidates
        class FakeProvider:
            def extract_text(self, image_path: Path) -> str:
                return "冒険"

        monkeypatch.setattr(scan_module, "build_ocr_provider",
                            lambda mode, **kw: FakeProvider())
        monkeypatch.setattr(scan_module, "get_default_normalizer",
                            lambda: _FakeNormalizer())

        data_dir = tmp_path / "data"
        from jp_anki_builder.scan import run_scan
        summary = run_scan(
            images=str(cbz),
            source="manga-a",
            run_id="ch01",
            base_dir=str(data_dir),
            ocr_mode="sidecar",
        )

        assert summary.image_count == 2
        artifact = data_dir / "manga-a" / "ch01" / "scan.json"
        assert artifact.exists()
        payload = json.loads(artifact.read_text(encoding="utf-8"))
        assert payload["image_count"] == 2
        assert len(payload["records"]) == 2

    def test_cbz_records_reference_page_names(self, tmp_path: Path, monkeypatch):
        from jp_anki_builder import scan as scan_module

        cbz = tmp_path / "manga.cbz"
        _make_cbz(cbz, ["page_01.png"])

        class FakeProvider:
            def extract_text(self, image_path: Path) -> str:
                return ""

        monkeypatch.setattr(scan_module, "build_ocr_provider",
                            lambda mode, **kw: FakeProvider())
        monkeypatch.setattr(scan_module, "get_default_normalizer",
                            lambda: _FakeNormalizer())

        data_dir = tmp_path / "data"
        from jp_anki_builder.scan import run_scan
        run_scan(
            images=str(cbz),
            source="manga-a",
            run_id="ch01",
            base_dir=str(data_dir),
            ocr_mode="sidecar",
        )

        payload = json.loads((data_dir / "manga-a" / "ch01" / "scan.json")
                             .read_text(encoding="utf-8"))
        # Record's "image" field should mention the page entry name
        assert "page_01.png" in payload["records"][0]["image"]


# ---------------------------------------------------------------------------
# Region detector integration: detector produces regions in scan.json
# ---------------------------------------------------------------------------

class TestScanWithNullDetector:
    """detector_mode='none' leaves scan.json identical to pre-Phase 2 format."""

    def test_null_detector_produces_no_regions_key_in_records(self, tmp_path: Path, monkeypatch):
        from jp_anki_builder import scan as scan_module

        images_dir = tmp_path / "images"
        images_dir.mkdir()
        img_path = images_dir / "panel.png"
        Image.new("RGB", (10, 10)).save(str(img_path))
        img_path.with_suffix(".txt").write_text("勇者", encoding="utf-8")

        data_dir = tmp_path / "data"
        from jp_anki_builder.scan import run_scan
        run_scan(
            images=str(images_dir),
            source="s",
            run_id="r",
            base_dir=str(data_dir),
            ocr_mode="sidecar",
            detector_mode="none",
        )

        payload = json.loads((data_dir / "s" / "r" / "scan.json")
                             .read_text(encoding="utf-8"))
        # "regions" key should NOT appear when detector_mode is "none"
        assert "regions" not in payload["records"][0]


class TestScanWithRegionDetector:
    """With a real detector, scan.json includes a 'regions' key per record."""

    def test_region_data_included_in_records(self, tmp_path: Path, monkeypatch):
        from jp_anki_builder import scan as scan_module
        from jp_anki_builder.ocr import DetectedRegion

        # Create a real image file
        images_dir = tmp_path / "images"
        images_dir.mkdir()
        img_path = images_dir / "page.png"
        Image.new("RGB", (100, 100)).save(str(img_path))

        # Fake OCR provider
        class FakeProvider:
            def extract_text(self, image_path: Path) -> str:
                return "冒険"

        # Fake detector that returns two regions
        class FakeDetector:
            def detect(self, page_image):
                return [
                    DetectedRegion(bbox=(0, 0, 50, 50), confidence=0.9),
                    DetectedRegion(bbox=(50, 50, 100, 100), confidence=0.8),
                ]

        monkeypatch.setattr(scan_module, "build_ocr_provider",
                            lambda mode, **kw: FakeProvider())
        monkeypatch.setattr(scan_module, "get_default_normalizer",
                            lambda: _FakeNormalizer())
        monkeypatch.setattr(scan_module, "build_region_detector",
                            lambda mode: FakeDetector())

        data_dir = tmp_path / "data"
        from jp_anki_builder.scan import run_scan
        run_scan(
            images=str(images_dir),
            source="s",
            run_id="r",
            base_dir=str(data_dir),
            ocr_mode="sidecar",
            detector_mode="paddleocr",
        )

        payload = json.loads((data_dir / "s" / "r" / "scan.json")
                             .read_text(encoding="utf-8"))
        record = payload["records"][0]
        assert "regions" in record
        assert len(record["regions"]) == 2
        assert record["regions"][0]["bbox"] == [0, 0, 50, 50]
        assert record["regions"][0]["confidence"] == pytest.approx(0.9)

    def test_text_from_all_regions_combined(self, tmp_path: Path, monkeypatch):
        from jp_anki_builder import scan as scan_module
        from jp_anki_builder.ocr import DetectedRegion

        images_dir = tmp_path / "images"
        images_dir.mkdir()
        img_path = images_dir / "page.png"
        Image.new("RGB", (200, 100)).save(str(img_path))

        region_texts = ["冒険", "勇者"]

        class FakeProvider:
            def __init__(self):
                self._call_count = 0

            def extract_text(self, image_path: Path) -> str:
                text = region_texts[self._call_count % len(region_texts)]
                self._call_count += 1
                return text

        class FakeDetector:
            def detect(self, page_image):
                return [
                    DetectedRegion(bbox=(0, 0, 100, 100), confidence=0.9),
                    DetectedRegion(bbox=(100, 0, 200, 100), confidence=0.85),
                ]

        fake_provider = FakeProvider()
        monkeypatch.setattr(scan_module, "build_ocr_provider",
                            lambda mode, **kw: fake_provider)
        monkeypatch.setattr(scan_module, "get_default_normalizer",
                            lambda: _FakeNormalizer())
        monkeypatch.setattr(scan_module, "build_region_detector",
                            lambda mode: FakeDetector())

        data_dir = tmp_path / "data"
        from jp_anki_builder.scan import run_scan
        run_scan(
            images=str(images_dir),
            source="s",
            run_id="r",
            base_dir=str(data_dir),
            ocr_mode="sidecar",
            detector_mode="paddleocr",
        )

        payload = json.loads((data_dir / "s" / "r" / "scan.json")
                             .read_text(encoding="utf-8"))
        record = payload["records"][0]
        # Combined text should include both region texts
        assert "冒険" in record["text"]
        assert "勇者" in record["text"]


# ---------------------------------------------------------------------------
# detector_mode plumbing: pipeline and CLI
# ---------------------------------------------------------------------------

class TestPipelinePassesDetectorMode:
    """Pipeline.scan() accepts and forwards detector_mode."""

    def test_pipeline_scan_accepts_detector_mode(self, tmp_path: Path, monkeypatch):
        import jp_anki_builder.pipeline as pipeline_module

        images_dir = tmp_path / "images"
        images_dir.mkdir()
        img = images_dir / "p.png"
        Image.new("RGB", (10, 10)).save(str(img))
        img.with_suffix(".txt").write_text("勇者", encoding="utf-8")

        captured = {}
        original_run_scan = pipeline_module.run_scan

        def fake_run_scan(*args, **kwargs):
            captured["detector_mode"] = kwargs.get("detector_mode")
            return original_run_scan(*args, **kwargs)

        # Patch the reference inside pipeline.py (where it's bound)
        monkeypatch.setattr(pipeline_module, "run_scan", fake_run_scan)

        from jp_anki_builder.pipeline import Pipeline
        Pipeline(data_dir=str(tmp_path / "data")).scan(
            images=str(images_dir),
            source="s",
            run_id="r",
            ocr_mode="sidecar",
            detector_mode="none",
        )

        assert captured["detector_mode"] == "none"


class TestCliPassesDetectorMode:
    """CLI scan command accepts --detector-mode and passes it through."""

    def test_scan_command_accepts_detector_mode_flag(self, tmp_path: Path):
        """--detector-mode is a valid flag and the scan succeeds with it."""
        images_dir = tmp_path / "images"
        images_dir.mkdir()
        img = images_dir / "p.png"
        Image.new("RGB", (10, 10)).save(str(img))
        img.with_suffix(".txt").write_text("勇者", encoding="utf-8")

        result = CliRunner().invoke(app, [
            "scan",
            "--images", str(images_dir),
            "--source", "s",
            "--run-id", "r",
            "--data-dir", str(tmp_path / "data"),
            "--ocr-mode", "sidecar",
            "--detector-mode", "none",
        ])

        assert result.exit_code == 0, result.output
        assert "[SCAN]" in result.output
