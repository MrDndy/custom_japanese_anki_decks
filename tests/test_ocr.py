from pathlib import Path

from jp_anki_builder import ocr as ocr_module
from jp_anki_builder.ocr import (
    DetectedRegion,
    MangaOcrProvider,
    OcrCandidate,
    OcrProvider,
    RegionDetector,
    SidecarOcrProvider,
    TesseractOcrProvider,
    build_ocr_provider,
)


def test_ocr_candidate_scoring_prefers_japanese_and_confidence():
    good = OcrCandidate(
        text="\u8db3 \u304c \u75db\u3044",
        confidence=85.0,
        config="--psm 7",
        preprocessed=False,
        language="jpn",
    )
    bad = OcrCandidate(
        text="???777",
        confidence=60.0,
        config="--psm 7",
        preprocessed=False,
        language="jpn",
    )

    assert TesseractOcrProvider._score_candidate(good) > TesseractOcrProvider._score_candidate(bad)


def test_ocr_normalize_removes_spaces_between_japanese_chars():
    raw = "\u8db3 \u304c \u75db \u3044"
    assert TesseractOcrProvider._normalize_text(raw) == "\u8db3\u304c\u75db\u3044"


def test_build_ocr_provider_supports_manga_ocr_mode():
    provider = build_ocr_provider("manga-ocr")
    assert provider.__class__.__name__ == "MangaOcrProvider"


def test_configure_manga_ocr_runtime_sets_default_env(monkeypatch):
    monkeypatch.setattr(ocr_module, "_MANGA_OCR_RUNTIME_CONFIGURED", False)
    monkeypatch.delenv("TRANSFORMERS_VERBOSITY", raising=False)
    monkeypatch.delenv("HF_HUB_DISABLE_PROGRESS_BARS", raising=False)
    monkeypatch.delenv("TOKENIZERS_PARALLELISM", raising=False)

    ocr_module._configure_manga_ocr_runtime()

    assert ocr_module.os.environ["TRANSFORMERS_VERBOSITY"] == "error"
    assert ocr_module.os.environ["HF_HUB_DISABLE_PROGRESS_BARS"] == "1"
    assert ocr_module.os.environ["TOKENIZERS_PARALLELISM"] == "false"


class TestOcrProviderProtocol:
    def test_sidecar_provider_satisfies_protocol(self):
        provider = SidecarOcrProvider()
        # Protocol is structural: check the method signature exists and is callable
        assert callable(provider.extract_text)
        import inspect
        sig = inspect.signature(provider.extract_text)
        assert "image_path" in sig.parameters

    def test_manga_ocr_provider_satisfies_protocol(self):
        provider = MangaOcrProvider()
        assert callable(provider.extract_text)

    def test_tesseract_provider_satisfies_protocol(self):
        provider = TesseractOcrProvider()
        assert callable(provider.extract_text)

    def test_build_ocr_provider_returns_sidecar(self):
        provider = build_ocr_provider("sidecar")
        assert isinstance(provider, SidecarOcrProvider)

    def test_build_ocr_provider_returns_tesseract(self):
        provider = build_ocr_provider("tesseract")
        assert isinstance(provider, TesseractOcrProvider)


class TestRegionDetectorProtocol:
    def test_region_detector_protocol_importable(self):
        from jp_anki_builder.ocr import RegionDetector
        import inspect
        assert inspect.isclass(RegionDetector)

    def test_region_detector_protocol_has_detect_method(self):
        from jp_anki_builder.ocr import RegionDetector
        import inspect
        # Protocol defines detect(page_image: np.ndarray) -> list[DetectedRegion]
        assert "detect" in {name for name, _ in inspect.getmembers(RegionDetector)}

    def test_concrete_class_satisfying_region_detector(self):
        from jp_anki_builder.ocr import DetectedRegion
        # A class with detect() structurally satisfies the Protocol
        class FakeDetector:
            def detect(self, page_image):
                return [DetectedRegion(bbox=(0, 0, 10, 10), confidence=0.9)]

        d = FakeDetector()
        result = d.detect(None)
        assert len(result) == 1
        assert isinstance(result[0], DetectedRegion)


class TestDetectedRegion:
    def test_detected_region_defaults(self):
        region = DetectedRegion(bbox=(0, 0, 100, 50), confidence=0.9)
        assert region.region_type == "text"
        assert region.mask is None
        assert region.bbox == (0, 0, 100, 50)
        assert region.confidence == 0.9

    def test_detected_region_custom_type(self):
        region = DetectedRegion(bbox=(10, 20, 30, 40), confidence=0.75, region_type="sfx")
        assert region.region_type == "sfx"
