import json
from pathlib import Path

from jp_anki_builder.dedup import exclude_seen
from jp_anki_builder.filtering import filter_tokens


def _load_candidates(path: Path) -> list[str]:
    return json.loads(path.read_text(encoding="utf-8-sig"))["candidates"]


def test_chapter2_skips_words_seen_in_chapter1(tmp_path):
    fixtures = Path(__file__).resolve().parents[1] / "fixtures"
    seen_path = tmp_path / "seen_words.json"

    seen_words: set[str] = set()
    ch1 = _load_candidates(fixtures / "sample_ocr_ch1.json")
    approved_ch1 = exclude_seen(filter_tokens(ch1, known_words=set()), seen_words)
    seen_words.update(approved_ch1)
    seen_path.write_text(
        json.dumps({"seen_words": sorted(seen_words)}, ensure_ascii=False),
        encoding="utf-8",
    )

    persisted = set(json.loads(seen_path.read_text(encoding="utf-8"))["seen_words"])
    ch2 = _load_candidates(fixtures / "sample_ocr_ch2.json")
    approved_ch2 = exclude_seen(filter_tokens(ch2, known_words=set()), persisted)

    assert approved_ch2 == ["町"]
