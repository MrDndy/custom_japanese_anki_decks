from __future__ import annotations

import numpy as np
import pytest


class TestNullDetector:
    """NullDetector returns a single region covering the full image."""

    def test_returns_one_region(self):
        from jp_anki_builder.region_detectors import build_region_detector

        detector = build_region_detector("none")
        img = np.zeros((100, 200, 3), dtype=np.uint8)
        regions = detector.detect(img)

        assert len(regions) == 1

    def test_region_covers_full_image_dimensions(self):
        from jp_anki_builder.region_detectors import build_region_detector

        detector = build_region_detector("none")
        img = np.zeros((150, 250, 3), dtype=np.uint8)
        regions = detector.detect(img)

        assert regions[0].bbox == (0, 0, 250, 150)  # (x1, y1, x2, y2) = (0, 0, w, h)

    def test_region_has_full_confidence(self):
        from jp_anki_builder.region_detectors import build_region_detector

        detector = build_region_detector("none")
        img = np.zeros((100, 100, 3), dtype=np.uint8)
        regions = detector.detect(img)

        assert regions[0].confidence == 1.0

    def test_different_image_sizes_produce_matching_bbox(self):
        from jp_anki_builder.region_detectors import build_region_detector

        detector = build_region_detector("none")
        for h, w in [(50, 80), (480, 640), (1080, 1920)]:
            img = np.zeros((h, w, 3), dtype=np.uint8)
            regions = detector.detect(img)
            assert regions[0].bbox == (0, 0, w, h)


class TestBuildRegionDetectorFactory:
    """build_region_detector factory dispatch."""

    def test_none_mode_returns_null_detector(self):
        from jp_anki_builder.region_detectors import NullDetector, build_region_detector

        result = build_region_detector("none")
        assert isinstance(result, NullDetector)

    def test_default_mode_is_none(self):
        from jp_anki_builder.region_detectors import NullDetector, build_region_detector

        result = build_region_detector()
        assert isinstance(result, NullDetector)

    def test_unsupported_mode_raises_value_error(self):
        from jp_anki_builder.region_detectors import build_region_detector

        with pytest.raises(ValueError, match="Unsupported detector"):
            build_region_detector("unknown_mode")

    def test_paddleocr_mode_returns_paddleocr_detector(self):
        from jp_anki_builder.region_detectors import PaddleOcrDetector, build_region_detector

        detector = build_region_detector("paddleocr")
        assert isinstance(detector, PaddleOcrDetector)


class TestPaddleOcrDetectorProtocolCompliance:
    """PaddleOcrDetector satisfies the RegionDetector Protocol."""

    def test_implements_region_detector_protocol(self):
        from jp_anki_builder.ocr import RegionDetector
        from jp_anki_builder.region_detectors import PaddleOcrDetector

        detector = PaddleOcrDetector()
        assert isinstance(detector, RegionDetector)

    def test_has_detect_method(self):
        from jp_anki_builder.region_detectors import PaddleOcrDetector

        assert hasattr(PaddleOcrDetector, "detect")

    def test_detect_raises_clear_error_when_paddleocr_missing(self, monkeypatch):
        from jp_anki_builder import region_detectors as rd_package
        from jp_anki_builder.region_detectors.paddleocr_detector import PaddleOcrDetector

        monkeypatch.setattr(
            "jp_anki_builder.region_detectors.paddleocr_detector._PADDLEOCR_AVAILABLE",
            False,
        )

        detector = PaddleOcrDetector()
        img = np.zeros((100, 100, 3), dtype=np.uint8)

        with pytest.raises(RuntimeError, match="paddleocr"):
            detector.detect(img)


class TestPaddleOcrDetectorLazyInit:
    """PaddleOcrDetector is lazily initialized on first detect() call."""

    def test_model_not_loaded_at_construction(self, monkeypatch):
        from jp_anki_builder.region_detectors.paddleocr_detector import PaddleOcrDetector

        detector = PaddleOcrDetector()
        # _engine should be None before first detect() call
        assert detector._engine is None

    def test_model_initialized_on_first_detect(self, monkeypatch):
        from jp_anki_builder.region_detectors.paddleocr_detector import PaddleOcrDetector

        init_calls = []

        class FakePaddleOCR:
            def __init__(self, **kwargs):
                init_calls.append(kwargs)

            def ocr(self, img, rec=False):
                # Return empty detection result
                return [[]]

        monkeypatch.setattr(
            "jp_anki_builder.region_detectors.paddleocr_detector._PADDLEOCR_AVAILABLE",
            True,
        )
        monkeypatch.setattr(
            "jp_anki_builder.region_detectors.paddleocr_detector._build_paddleocr",
            lambda: FakePaddleOCR(),
        )

        detector = PaddleOcrDetector()
        assert detector._engine is None  # not yet initialized

        img = np.zeros((100, 100, 3), dtype=np.uint8)
        detector.detect(img)

        assert detector._engine is not None  # now initialized


class TestDetectorModeInProjectConfig:
    """detector_mode is a valid config key in ProjectDefaults."""

    def test_detector_mode_field_exists_on_project_defaults(self):
        from jp_anki_builder.project_config import ProjectDefaults

        defaults = ProjectDefaults()
        assert hasattr(defaults, "detector_mode")

    def test_detector_mode_defaults_to_none_string(self):
        from jp_anki_builder.project_config import ProjectDefaults

        defaults = ProjectDefaults()
        assert defaults.detector_mode is None  # None means "not set"

    def test_set_config_accepts_detector_mode(self, tmp_path):
        from jp_anki_builder.project_config import get_config, set_config

        set_config("detector_mode", "paddleocr", data_dir=str(tmp_path))
        cfg = get_config(data_dir=str(tmp_path))
        assert cfg["detector_mode"] == "paddleocr"

    def test_load_project_config_reads_detector_mode(self, tmp_path):
        import json
        from jp_anki_builder.project_config import load_project_config

        cfg_file = tmp_path / ".jp-anki.json"
        cfg_file.write_text(json.dumps({"detector_mode": "paddleocr"}), encoding="utf-8")

        defaults = load_project_config(data_dir=str(tmp_path))
        assert defaults.detector_mode == "paddleocr"
