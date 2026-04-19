from __future__ import annotations

"""Integration tests for the full-page Phase 2 pipeline (Task 2.07).

Covers end-to-end scenarios using synthetic fixtures:
- NullDetector full-page scan (backward-compatible screenshot mode)
- CBZ input → page extraction → scan pipeline
- Spread detection → split and scan
- PDF with embedded text (pdfplumber path, mocked)
- PDF with image-only pages (pypdfium2 path, mocked)
- Resume with region-aware scan.json
- Phase 1 filters still applied with region-detected text
- PaddleOCR detection (skipped if not installed)
- Backward compatibility: pre-Phase-2 screenshot workflow unchanged
"""

import io
import json
import zipfile
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from PIL import Image

from jp_anki_builder.normalization import NormalizedCandidate
from jp_anki_builder.ocr import DetectedRegion
from jp_anki_builder.scan import run_scan


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _make_cbz(path: Path, pages: int = 3) -> None:
    """Write a CBZ with *pages* numbered blank PNG images."""
    with zipfile.ZipFile(path, "w") as zf:
        for i in range(pages):
            buf = io.BytesIO()
            Image.new("RGB", (40, 40), color=(220, 220, 220)).save(buf, format="PNG")
            zf.writestr(f"page_{i + 1:02d}.png", buf.getvalue())


def _make_wide_image(path: Path, width: int = 200, height: int = 80) -> None:
    """Write a wide (spread-aspect) PNG image."""
    Image.new("RGB", (width, height), color=(180, 180, 180)).save(str(path))


def _make_image(path: Path, size: tuple[int, int] = (40, 40)) -> None:
    Image.new("RGB", size, color=(200, 200, 200)).save(str(path))


class FakeNormalizer:
    method_name = "rule_based"

    def normalize_text(self, text: str, word_exists=None) -> list[NormalizedCandidate]:
        return []


class FakeProvider:
    """OCR provider that returns a fixed string."""

    def __init__(self, text: str = "冒険") -> None:
        self._text = text

    def extract_text(self, image_path: Path) -> str:
        return self._text


class CountingProvider:
    """OCR provider that counts calls and returns texts from a list."""

    def __init__(self, texts: list[str]) -> None:
        self._texts = texts
        self.calls: list[Path] = []

    def extract_text(self, image_path: Path) -> str:
        self.calls.append(image_path)
        return self._texts[(len(self.calls) - 1) % len(self._texts)]


# ---------------------------------------------------------------------------
# Test: NullDetector full-page scan (backward-compatible)
# ---------------------------------------------------------------------------


class TestNullDetectorFullPageScan:
    """With detector_mode='none' and a directory of images, pipeline is identical to pre-Phase-2."""

    def test_screenshot_mode_produces_no_regions_key(self, tmp_path: Path, monkeypatch) -> None:
        import jp_anki_builder.scan as scan_module

        images_dir = tmp_path / "images"
        images_dir.mkdir()
        _make_image(images_dir / "panel.png")
        (images_dir / "panel.txt").write_text("勇者", encoding="utf-8")

        monkeypatch.setattr(scan_module, "build_ocr_provider", lambda mode, **kw: FakeProvider("勇者"))
        monkeypatch.setattr(scan_module, "get_default_normalizer", lambda: FakeNormalizer())

        summary = run_scan(
            images=str(images_dir),
            source="s",
            run_id="r",
            base_dir=str(tmp_path / "data"),
            ocr_mode="sidecar",
            detector_mode="none",
        )

        artifact = tmp_path / "data" / "s" / "r" / "scan.json"
        payload = json.loads(artifact.read_text(encoding="utf-8"))
        record = payload["records"][0]
        assert "regions" not in record, "NullDetector mode must not add 'regions' key"
        assert summary.image_count == 1

    def test_screenshot_mode_text_extracted_from_sidecar(self, tmp_path: Path, monkeypatch) -> None:
        """Sidecar .txt file is picked up correctly in screenshot mode."""
        import jp_anki_builder.scan as scan_module

        images_dir = tmp_path / "images"
        images_dir.mkdir()
        _make_image(images_dir / "frame.png")
        (images_dir / "frame.txt").write_text("魔法", encoding="utf-8")

        monkeypatch.setattr(scan_module, "build_ocr_provider", lambda mode, **kw: FakeProvider("魔法"))
        monkeypatch.setattr(scan_module, "get_default_normalizer", lambda: FakeNormalizer())

        run_scan(
            images=str(images_dir),
            source="s",
            run_id="r",
            base_dir=str(tmp_path / "data"),
            ocr_mode="sidecar",
            detector_mode="none",
        )

        payload = json.loads((tmp_path / "data" / "s" / "r" / "scan.json")
                             .read_text(encoding="utf-8"))
        assert payload["records"][0]["text"] == "魔法"


# ---------------------------------------------------------------------------
# Test: CBZ input → page extraction → scan pipeline
# ---------------------------------------------------------------------------


class TestCbzInputToScanPipeline:
    """CBZ file is extracted page-by-page and each page is scanned."""

    def test_cbz_three_pages_produces_three_records(self, tmp_path: Path, monkeypatch) -> None:
        import jp_anki_builder.scan as scan_module

        cbz = tmp_path / "ch01.cbz"
        _make_cbz(cbz, pages=3)

        monkeypatch.setattr(scan_module, "build_ocr_provider", lambda mode, **kw: FakeProvider("勇者"))
        monkeypatch.setattr(scan_module, "get_default_normalizer", lambda: FakeNormalizer())

        summary = run_scan(
            images=str(cbz),
            source="manga",
            run_id="ch01",
            base_dir=str(tmp_path / "data"),
            ocr_mode="sidecar",
        )

        assert summary.image_count == 3
        payload = json.loads((tmp_path / "data" / "manga" / "ch01" / "scan.json")
                             .read_text(encoding="utf-8"))
        assert len(payload["records"]) == 3

    def test_cbz_pages_naturally_sorted(self, tmp_path: Path, monkeypatch) -> None:
        """Pages extracted from CBZ are in natural sort order."""
        import jp_anki_builder.scan as scan_module

        cbz = tmp_path / "ch.cbz"
        names = ["page_10.png", "page_2.png", "page_1.png"]
        with zipfile.ZipFile(cbz, "w") as zf:
            for name in names:
                buf = io.BytesIO()
                Image.new("RGB", (10, 10)).save(buf, format="PNG")
                zf.writestr(name, buf.getvalue())

        monkeypatch.setattr(scan_module, "build_ocr_provider", lambda mode, **kw: FakeProvider(""))
        monkeypatch.setattr(scan_module, "get_default_normalizer", lambda: FakeNormalizer())

        run_scan(
            images=str(cbz),
            source="s",
            run_id="r",
            base_dir=str(tmp_path / "data"),
            ocr_mode="sidecar",
        )

        payload = json.loads((tmp_path / "data" / "s" / "r" / "scan.json")
                             .read_text(encoding="utf-8"))
        images_in_order = [r["image"] for r in payload["records"]]
        # natural sort: page_1 < page_2 < page_10
        assert "page_1.png" in images_in_order[0]
        assert "page_2.png" in images_in_order[1]
        assert "page_10.png" in images_in_order[2]

    def test_cbz_with_null_detector_no_regions_in_records(self, tmp_path: Path, monkeypatch) -> None:
        import jp_anki_builder.scan as scan_module

        cbz = tmp_path / "ch.cbz"
        _make_cbz(cbz, pages=2)

        monkeypatch.setattr(scan_module, "build_ocr_provider", lambda mode, **kw: FakeProvider(""))
        monkeypatch.setattr(scan_module, "get_default_normalizer", lambda: FakeNormalizer())

        run_scan(
            images=str(cbz),
            source="s",
            run_id="r",
            base_dir=str(tmp_path / "data"),
            ocr_mode="sidecar",
            detector_mode="none",
        )

        payload = json.loads((tmp_path / "data" / "s" / "r" / "scan.json")
                             .read_text(encoding="utf-8"))
        for record in payload["records"]:
            assert "regions" not in record


# ---------------------------------------------------------------------------
# Test: Spread detection → split → scan each half
# ---------------------------------------------------------------------------


class TestSpreadDetectionInPipeline:
    """detect_and_split_spread is available and returns correct halves."""

    def test_wide_image_split_into_right_then_left(self) -> None:
        """Right half first (Japanese reading order)."""
        from jp_anki_builder.format_handlers import detect_and_split_spread

        wide = Image.new("RGB", (200, 80), color=(100, 150, 200))
        halves = detect_and_split_spread(wide, threshold=1.3)

        assert len(halves) == 2
        # Both halves should be 100×80
        assert halves[0].size == (100, 80)
        assert halves[1].size == (100, 80)

    def test_normal_image_not_split(self) -> None:
        from jp_anki_builder.format_handlers import detect_and_split_spread

        normal = Image.new("RGB", (80, 100))
        result = detect_and_split_spread(normal, threshold=1.3)
        assert len(result) == 1
        assert result[0] is normal

    def test_split_returns_right_half_first(self) -> None:
        """Pixel values confirm right half is element [0]."""
        from jp_anki_builder.format_handlers import detect_and_split_spread

        # Left half red, right half blue
        wide = Image.new("RGB", (200, 10))
        left = Image.new("RGB", (100, 10), color=(255, 0, 0))
        right = Image.new("RGB", (100, 10), color=(0, 0, 255))
        wide.paste(left, (0, 0))
        wide.paste(right, (100, 0))

        halves = detect_and_split_spread(wide, threshold=1.3)

        # halves[0] should be blue (right/second half)
        assert halves[0].getpixel((5, 5)) == (0, 0, 255)
        # halves[1] should be red (left/first half)
        assert halves[1].getpixel((5, 5)) == (255, 0, 0)


# ---------------------------------------------------------------------------
# Test: PDF with embedded text (pdfplumber path, mocked)
# ---------------------------------------------------------------------------


class TestPdfEmbeddedTextExtraction:
    """PDF text layer is extracted via pdfplumber; OCR is skipped."""

    def test_pdf_text_layer_used_without_ocr(self, tmp_path: Path, monkeypatch) -> None:
        import jp_anki_builder.format_handlers as fh_module
        import jp_anki_builder.scan as scan_module

        # Mock pdfplumber returning Japanese text
        mock_page = MagicMock()
        mock_page.extract_text.return_value = "魔法使いの世界へ"

        mock_pdf = MagicMock()
        mock_pdf.__enter__ = lambda s: s
        mock_pdf.__exit__ = MagicMock(return_value=False)
        mock_pdf.pages = [mock_page]

        monkeypatch.setattr(fh_module, "_PDFPLUMBER_AVAILABLE", True)
        monkeypatch.setattr(fh_module, "_open_pdfplumber", lambda path: mock_pdf)

        ocr_calls: list = []

        class SpyProvider:
            def extract_text(self, image_path: Path) -> str:
                ocr_calls.append(image_path)
                return ""

        monkeypatch.setattr(scan_module, "build_ocr_provider", lambda mode, **kw: SpyProvider())
        monkeypatch.setattr(scan_module, "get_default_normalizer", lambda: FakeNormalizer())

        # Create a fake .pdf file (content doesn't matter — pdfplumber is mocked)
        pdf_path = tmp_path / "manga.pdf"
        pdf_path.write_bytes(b"%PDF-1.4")

        run_scan(
            images=str(pdf_path),
            source="s",
            run_id="r",
            base_dir=str(tmp_path / "data"),
            ocr_mode="sidecar",
        )

        # OCR should NOT have been called because text layer provided text
        assert len(ocr_calls) == 0

        payload = json.loads((tmp_path / "data" / "s" / "r" / "scan.json")
                             .read_text(encoding="utf-8"))
        assert payload["records"][0]["text"] == "魔法使いの世界へ"

    def test_pdf_without_japanese_text_falls_through_to_ocr(self, tmp_path: Path, monkeypatch) -> None:
        """If pdfplumber finds no CJK text, the page is rendered and OCR'd."""
        import jp_anki_builder.format_handlers as fh_module
        import jp_anki_builder.scan as scan_module

        mock_page = MagicMock()
        mock_page.extract_text.return_value = "no japanese here"

        mock_pdf = MagicMock()
        mock_pdf.__enter__ = lambda s: s
        mock_pdf.__exit__ = MagicMock(return_value=False)
        mock_pdf.pages = [mock_page]

        # Mock pypdfium2 renderer
        mock_pil_image = Image.new("RGB", (20, 20))
        mock_render = MagicMock()
        mock_render.to_pil.return_value = mock_pil_image
        mock_pdfpage = MagicMock()
        mock_pdfpage.render.return_value = mock_render
        mock_pdfium_doc = MagicMock()
        mock_pdfium_doc.__iter__ = lambda s: iter([mock_pdfpage])
        mock_pdfium_doc.__getitem__ = lambda s, i: mock_pdfpage

        monkeypatch.setattr(fh_module, "_PDFPLUMBER_AVAILABLE", True)
        monkeypatch.setattr(fh_module, "_PYPDFIUM2_AVAILABLE", True)
        monkeypatch.setattr(fh_module, "_open_pdfplumber", lambda path: mock_pdf)
        monkeypatch.setattr(fh_module, "_open_pypdfium2", lambda path: mock_pdfium_doc)

        ocr_calls: list = []

        class SpyProvider:
            def extract_text(self, image_path: Path) -> str:
                ocr_calls.append(image_path)
                return "勇者"

        monkeypatch.setattr(scan_module, "build_ocr_provider", lambda mode, **kw: SpyProvider())
        monkeypatch.setattr(scan_module, "get_default_normalizer", lambda: FakeNormalizer())

        pdf_path = tmp_path / "scanned.pdf"
        pdf_path.write_bytes(b"%PDF-1.4")

        run_scan(
            images=str(pdf_path),
            source="s",
            run_id="r",
            base_dir=str(tmp_path / "data"),
            ocr_mode="sidecar",
        )

        assert len(ocr_calls) == 1, "OCR should be called once for image-only PDF page"


# ---------------------------------------------------------------------------
# Test: Resume with region-aware scan.json
# ---------------------------------------------------------------------------


class TestResumeWithRegionAwareScanJson:
    """--resume correctly skips already-processed pages in region-aware format."""

    def test_resume_skips_completed_pages(self, tmp_path: Path, monkeypatch) -> None:
        import jp_anki_builder.scan as scan_module

        cbz = tmp_path / "ch.cbz"
        _make_cbz(cbz, pages=3)

        call_count = [0]

        class CountingProvider:
            def extract_text(self, image_path: Path) -> str:
                call_count[0] += 1
                return "勇者"

        monkeypatch.setattr(scan_module, "build_ocr_provider", lambda mode, **kw: CountingProvider())
        monkeypatch.setattr(scan_module, "get_default_normalizer", lambda: FakeNormalizer())

        data_dir = str(tmp_path / "data")

        # First scan: process all 3 pages
        run_scan(
            images=str(cbz),
            source="s",
            run_id="r",
            base_dir=data_dir,
            ocr_mode="sidecar",
        )
        assert call_count[0] == 3

        # Second scan with resume: should skip all 3 pages
        call_count[0] = 0
        summary = run_scan(
            images=str(cbz),
            source="s",
            run_id="r",
            base_dir=data_dir,
            ocr_mode="sidecar",
            resume=True,
        )

        assert call_count[0] == 0, "Resume should skip already-processed pages"
        assert summary.resumed is True
        assert summary.image_count == 3

    def test_resume_processes_only_remaining_pages(self, tmp_path: Path, monkeypatch) -> None:
        """Partial scan with 1/3 pages done → resume processes only 2 remaining."""
        import jp_anki_builder.scan as scan_module
        from jp_anki_builder.config import RunPaths

        cbz = tmp_path / "ch.cbz"
        names = ["page_01.png", "page_02.png", "page_03.png"]
        with zipfile.ZipFile(cbz, "w") as zf:
            for name in names:
                buf = io.BytesIO()
                Image.new("RGB", (10, 10)).save(buf, format="PNG")
                zf.writestr(name, buf.getvalue())

        # Write a partial scan.json manually with 1 of 3 pages done.
        # CBZ source_file is just the entry name within the zip (e.g. "page_01.png").
        paths = RunPaths(base_dir=str(tmp_path / "data"), source_id="s", run_id="r")
        paths.run_dir.mkdir(parents=True, exist_ok=True)
        partial = {
            "source": "s", "run_id": "r", "ocr_mode": "sidecar",
            "ocr_language": "jpn", "normalization_method": "rule_based",
            "online_dict": "off", "image_count": 3,
            "records": [
                {"image": "page_01.png", "text": "冒険",
                 "alternate_texts": [], "surface_tokens": [],
                 "normalized_candidates": [], "candidates": ["冒険"]},
            ],
            "candidates": ["冒険"],
        }
        paths.scan_artifact.write_text(json.dumps(partial, ensure_ascii=False), encoding="utf-8")

        call_count = [0]

        class CountingProvider:
            def extract_text(self, image_path: Path) -> str:
                call_count[0] += 1
                return "勇者"

        monkeypatch.setattr(scan_module, "build_ocr_provider", lambda mode, **kw: CountingProvider())
        monkeypatch.setattr(scan_module, "get_default_normalizer", lambda: FakeNormalizer())

        run_scan(
            images=str(cbz),
            source="s",
            run_id="r",
            base_dir=str(tmp_path / "data"),
            ocr_mode="sidecar",
            resume=True,
        )

        assert call_count[0] == 2, "Should only process the 2 remaining pages"

        payload = json.loads(paths.scan_artifact.read_text(encoding="utf-8"))
        assert len(payload["records"]) == 3

    def test_resume_with_region_records_in_scan_json(self, tmp_path: Path, monkeypatch) -> None:
        """Partial scan.json with regions key is handled correctly on resume."""
        import jp_anki_builder.scan as scan_module
        from jp_anki_builder.config import RunPaths

        images_dir = tmp_path / "images"
        images_dir.mkdir()
        for i in range(2):
            _make_image(images_dir / f"p{i+1}.png")

        paths = RunPaths(base_dir=str(tmp_path / "data"), source_id="s", run_id="r")
        paths.run_dir.mkdir(parents=True, exist_ok=True)
        # Partial scan with region data already in first record
        partial = {
            "source": "s", "run_id": "r", "ocr_mode": "sidecar",
            "ocr_language": "jpn", "normalization_method": "rule_based",
            "online_dict": "off", "image_count": 2,
            "records": [
                {
                    "image": str(images_dir / "p1.png"),
                    "text": "魔法",
                    "alternate_texts": [], "surface_tokens": [],
                    "normalized_candidates": [], "candidates": [],
                    "regions": [{"bbox": [0, 0, 40, 40], "confidence": 0.9, "text": "魔法"}],
                },
            ],
            "candidates": [],
        }
        paths.scan_artifact.write_text(json.dumps(partial, ensure_ascii=False), encoding="utf-8")

        monkeypatch.setattr(scan_module, "build_ocr_provider", lambda mode, **kw: FakeProvider("勇者"))
        monkeypatch.setattr(scan_module, "get_default_normalizer", lambda: FakeNormalizer())

        run_scan(
            images=str(images_dir),
            source="s",
            run_id="r",
            base_dir=str(tmp_path / "data"),
            ocr_mode="sidecar",
            resume=True,
        )

        payload = json.loads(paths.scan_artifact.read_text(encoding="utf-8"))
        assert len(payload["records"]) == 2
        # First record preserved with regions
        assert payload["records"][0]["regions"][0]["confidence"] == pytest.approx(0.9)


# ---------------------------------------------------------------------------
# Test: Phase 1 filters work with region-detected text
# ---------------------------------------------------------------------------


class TestPhase1FiltersWithRegionDetectedText:
    """SFX filtering, furigana filtering, etc. still apply to region-aggregated text."""

    def test_region_aggregated_text_goes_through_normalization(self, tmp_path: Path, monkeypatch) -> None:
        """Candidates from region-detected text are processed by the normalizer."""
        import jp_anki_builder.scan as scan_module

        images_dir = tmp_path / "images"
        images_dir.mkdir()
        _make_image(images_dir / "page.png", size=(500, 500))

        normalized_called_with: list[str] = []

        class TrackingNormalizer:
            method_name = "rule_based"

            def normalize_text(self, text: str, word_exists=None) -> list[NormalizedCandidate]:
                normalized_called_with.append(text)
                return []

        class FakeDetector:
            def detect(self, page_image):
                # Regions placed far apart so they won't be merged by
                # _merge_nearby_regions (gap_threshold=40).
                return [
                    DetectedRegion(bbox=(10, 10, 60, 60), confidence=0.9),
                    DetectedRegion(bbox=(200, 200, 300, 300), confidence=0.85),
                ]

        region_texts = ["冒険", "勇者"]
        call_idx = [0]

        class RegionProvider:
            def extract_text(self, image_path: Path) -> str:
                text = region_texts[call_idx[0] % len(region_texts)]
                call_idx[0] += 1
                return text

        monkeypatch.setattr(scan_module, "build_ocr_provider", lambda mode, **kw: RegionProvider())
        monkeypatch.setattr(scan_module, "get_default_normalizer", lambda: TrackingNormalizer())
        monkeypatch.setattr(scan_module, "build_region_detector", lambda mode: FakeDetector())

        run_scan(
            images=str(images_dir),
            source="s",
            run_id="r",
            base_dir=str(tmp_path / "data"),
            ocr_mode="sidecar",
            detector_mode="paddleocr",
        )

        # Normalizer should have been called with the combined text
        assert len(normalized_called_with) >= 1
        combined_text = normalized_called_with[0]
        assert "冒険" in combined_text
        assert "勇者" in combined_text

    def test_scan_artifact_has_candidates_from_region_scan(self, tmp_path: Path, monkeypatch) -> None:
        """scan.json records have candidates list even in region-aware mode."""
        import jp_anki_builder.scan as scan_module

        images_dir = tmp_path / "images"
        images_dir.mkdir()
        _make_image(images_dir / "page.png", size=(100, 100))

        class FakeDetector:
            def detect(self, page_image):
                return [DetectedRegion(bbox=(0, 0, 100, 100), confidence=0.95)]

        monkeypatch.setattr(scan_module, "build_ocr_provider", lambda mode, **kw: FakeProvider("勇者"))
        monkeypatch.setattr(scan_module, "get_default_normalizer", lambda: FakeNormalizer())
        monkeypatch.setattr(scan_module, "build_region_detector", lambda mode: FakeDetector())

        run_scan(
            images=str(images_dir),
            source="s",
            run_id="r",
            base_dir=str(tmp_path / "data"),
            ocr_mode="sidecar",
            detector_mode="paddleocr",
        )

        payload = json.loads((tmp_path / "data" / "s" / "r" / "scan.json")
                             .read_text(encoding="utf-8"))
        record = payload["records"][0]
        assert "candidates" in record
        assert "regions" in record


# ---------------------------------------------------------------------------
# Test: PaddleOCR detection (skip if not installed)
# ---------------------------------------------------------------------------


class TestPaddleOcrDetector:
    """PaddleOCR region detector works end-to-end when installed."""

    def test_paddleocr_detector_skipped_when_not_installed(self) -> None:
        from jp_anki_builder.region_detectors import build_region_detector

        try:
            import paddleocr  # noqa: F401
        except ImportError:
            pytest.skip("PaddleOCR not installed")

        # If PaddleOCR IS installed, just verify build_region_detector returns something callable
        detector = build_region_detector("paddleocr")
        assert hasattr(detector, "detect")

    def test_paddleocr_missing_raises_clear_error(self, monkeypatch) -> None:
        import jp_anki_builder.region_detectors.paddleocr_detector as pd_module

        monkeypatch.setattr(pd_module, "_PADDLEOCR_AVAILABLE", False)
        from jp_anki_builder.region_detectors.paddleocr_detector import PaddleOcrDetector
        import numpy as np

        detector = PaddleOcrDetector()
        with pytest.raises((RuntimeError, ImportError)):
            detector.detect(np.zeros((10, 10, 3), dtype=np.uint8))


# ---------------------------------------------------------------------------
# Test: Backward compatibility — existing screenshot workflow unchanged
# ---------------------------------------------------------------------------


class TestBackwardCompatibilityScreenshotWorkflow:
    """Pre-Phase-2 screenshot workflow produces identical output with new code."""

    def test_directory_of_images_processed_without_container_path(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        import jp_anki_builder.scan as scan_module

        images_dir = tmp_path / "screenshots"
        images_dir.mkdir()
        for i in range(3):
            _make_image(images_dir / f"shot_{i+1:02d}.png")
            (images_dir / f"shot_{i+1:02d}.txt").write_text(f"テスト{i}", encoding="utf-8")

        monkeypatch.setattr(scan_module, "build_ocr_provider",
                            lambda mode, **kw: FakeProvider("テスト"))
        monkeypatch.setattr(scan_module, "get_default_normalizer", lambda: FakeNormalizer())

        summary = run_scan(
            images=str(images_dir),
            source="shots",
            run_id="run1",
            base_dir=str(tmp_path / "data"),
            ocr_mode="sidecar",
            detector_mode="none",
        )

        assert summary.image_count == 3
        assert summary.resumed is False

        payload = json.loads((tmp_path / "data" / "shots" / "run1" / "scan.json")
                             .read_text(encoding="utf-8"))
        assert len(payload["records"]) == 3
        for record in payload["records"]:
            assert "regions" not in record, "Screenshot mode must not add regions"
            assert "text" in record
            assert "candidates" in record

    def test_single_image_file_processed_correctly(self, tmp_path: Path, monkeypatch) -> None:
        import jp_anki_builder.scan as scan_module

        img_path = tmp_path / "screenshot.png"
        _make_image(img_path)
        img_path.with_suffix(".txt").write_text("魔法", encoding="utf-8")

        monkeypatch.setattr(scan_module, "build_ocr_provider",
                            lambda mode, **kw: FakeProvider("魔法"))
        monkeypatch.setattr(scan_module, "get_default_normalizer", lambda: FakeNormalizer())

        summary = run_scan(
            images=str(img_path),
            source="s",
            run_id="r",
            base_dir=str(tmp_path / "data"),
            ocr_mode="sidecar",
        )

        assert summary.image_count == 1

    def test_alternate_texts_preserved_in_screenshot_mode(self, tmp_path: Path, monkeypatch) -> None:
        """extract_text_candidates() results are stored as alternate_texts in screenshot mode."""
        import jp_anki_builder.scan as scan_module

        images_dir = tmp_path / "images"
        images_dir.mkdir()
        _make_image(images_dir / "p.png")

        class MultiCandidateProvider:
            def extract_text(self, image_path: Path) -> str:
                return "勇者"

            def extract_text_candidates(self, image_path: Path, top_n: int = 8) -> list[str]:
                return ["勇者", "勇士", "戦士"]

        monkeypatch.setattr(scan_module, "build_ocr_provider",
                            lambda mode, **kw: MultiCandidateProvider())
        monkeypatch.setattr(scan_module, "get_default_normalizer", lambda: FakeNormalizer())

        run_scan(
            images=str(images_dir),
            source="s",
            run_id="r",
            base_dir=str(tmp_path / "data"),
            ocr_mode="sidecar",
            detector_mode="none",
        )

        payload = json.loads((tmp_path / "data" / "s" / "r" / "scan.json")
                             .read_text(encoding="utf-8"))
        record = payload["records"][0]
        assert record["text"] == "勇者"
        assert "勇士" in record.get("alternate_texts", [])

    def test_unsupported_extension_raises(self, tmp_path: Path) -> None:
        """Unsupported file extension raises ValueError."""
        fake_file = tmp_path / "manga.xyz"
        fake_file.write_bytes(b"fake")

        with pytest.raises(ValueError, match="No pages found|No image files found"):
            run_scan(
                images=str(fake_file),
                source="s",
                run_id="r",
                base_dir=str(tmp_path / "data"),
                ocr_mode="sidecar",
            )
