from jp_anki_builder.ocr import OcrCandidate, TesseractOcrProvider


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
    raw = "足 が 痛 い"
    assert TesseractOcrProvider._normalize_text(raw) == "足が痛い"
