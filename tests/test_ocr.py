from jp_anki_builder import ocr as ocr_module
from jp_anki_builder.ocr import OcrCandidate, TesseractOcrProvider, build_ocr_provider


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
