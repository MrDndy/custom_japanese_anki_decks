from jp_anki_builder.ocr import OcrCandidate, TesseractOcrProvider


def test_ocr_candidate_scoring_prefers_japanese_and_confidence():
    good = OcrCandidate(text="\u8db3 \u304c \u75db\u3044", confidence=85.0, config="--psm 7", preprocessed=False)
    bad = OcrCandidate(text="???777", confidence=60.0, config="--psm 7", preprocessed=False)

    assert TesseractOcrProvider._score_candidate(good) > TesseractOcrProvider._score_candidate(bad)
