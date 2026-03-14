"""OCR confusable character correction for Japanese text.

Generates candidate corrections for common OCR misreads where
visually similar characters are confused. Each substitution produces
an alternative candidate that should be validated against a dictionary.
"""

from __future__ import annotations

from collections.abc import Callable

# Bidirectional confusable pairs: OCR may swap either direction.
# Each pair is (char_a, char_b) — we try both substitutions.
_CONFUSABLE_PAIRS: list[tuple[str, str]] = [
    ("ー", "一"),  # katakana prolonged sound mark vs kanji "one"
    ("ロ", "口"),  # katakana "ro" vs kanji "mouth"
    ("カ", "力"),  # katakana "ka" vs kanji "power"
    ("ニ", "二"),  # katakana "ni" vs kanji "two"
    ("エ", "工"),  # katakana "e" vs kanji "craft"
    ("タ", "夕"),  # katakana "ta" vs kanji "evening"
    ("ハ", "八"),  # katakana "ha" vs kanji "eight"
    ("ぺ", "べ"),  # handakuten vs dakuten confusion
    ("ぱ", "ば"),
    ("ぴ", "び"),
    ("ぷ", "ぶ"),
    ("ぽ", "ぼ"),
    ("ペ", "ベ"),
    ("パ", "バ"),
    ("ピ", "ビ"),
    ("プ", "ブ"),
    ("ポ", "ボ"),
]

# Build lookup: char -> list of possible corrections
_CORRECTIONS: dict[str, list[str]] = {}
for _a, _b in _CONFUSABLE_PAIRS:
    _CORRECTIONS.setdefault(_a, []).append(_b)
    _CORRECTIONS.setdefault(_b, []).append(_a)


def ocr_correction_candidates(text: str, max_candidates: int = 8) -> list[str]:
    """Generate correction candidates by substituting confusable characters.

    Tries single-character substitutions (one at a time) to keep the
    candidate count manageable. Returns candidates in order of position.
    """
    candidates: list[str] = []
    seen: set[str] = {text}

    for i, ch in enumerate(text):
        corrections = _CORRECTIONS.get(ch)
        if not corrections:
            continue
        for replacement in corrections:
            variant = text[:i] + replacement + text[i + 1 :]
            if variant not in seen:
                seen.add(variant)
                candidates.append(variant)
                if len(candidates) >= max_candidates:
                    return candidates

    return candidates


def correct_with_dictionary(
    text: str,
    word_exists: Callable[[str], bool],
) -> str | None:
    """Return the first dictionary-validated OCR correction, or None."""
    for candidate in ocr_correction_candidates(text):
        if word_exists(candidate):
            return candidate
    return None
