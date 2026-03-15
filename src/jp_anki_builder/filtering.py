"""Candidate filtering: particles, stop words, SFX detection, and furigana noise removal."""
from __future__ import annotations

import re
from collections.abc import Callable

_KATAKANA_ONLY = re.compile(r"^[\u30A0-\u30FF]+$")
_SINGLE_HIRAGANA = re.compile(r"^[\u3041-\u309F]$")
_HAS_KANJI = re.compile(r"[\u4E00-\u9FFF\u3400-\u4DBF]")


def is_sfx_token(token: str, word_exists: Callable[[str], bool] | None = None) -> bool:
    """Return True if *token* is likely a sound effect / onomatopoeia.

    Rule 1: same katakana character repeated 2+ times (e.g. ドドド, ゴゴゴ).
    Rule 2: pure katakana of 2–4 characters with no offline dictionary match
             (only applied when *word_exists* is provided).
    """
    if not token or not _KATAKANA_ONLY.match(token):
        return False
    if len(token) >= 2 and len(set(token)) == 1:
        return True
    if 2 <= len(token) <= 4 and word_exists is not None and not word_exists(token):
        return True
    return False


DEFAULT_PARTICLES = {
    "\u306f",
    "\u304c",
    "\u3092",
    "\u306b",
    "\u3067",
    "\u3068",
    "\u3082",
    "\u306e",
    "\u3078",
    "\u304b",
    "\u306a\u3041",
    "\u4e00",
    "\u4e8c",
    "\u4e09",
    "\u56db",
    "\u4e94",
    "\u516d",
    "\u4e03",
    "\u516b",
    "\u4e5d",
    "\u5341",
    "\u4eba",
    "\u3059\u308b",
    "\u70ba\u308b",
    "\u3044\u308b",
    "\u5c45\u308b",
    "\u3066\u308b",
    "\u3053\u306e",
    "\u305d\u306e",
    "\u3042\u306e",
    "\u3069\u306e",
    "\u3082\u306e",
    "\u3072\u3068",
    "\u307e\u3067",
    "\u304b\u3089",
    "\u306a\u3093",
    "\u3053\u3053",
    "\u3059\u3050",
    "\u3084\u308b",
    "\u3088\u301c",
    "\u306a\u301c",
    "\u304a\u3044\u3063",
    "\u30ca\u30f3\u30c0\u30ab\u30e9",
    "\u30b1",
    "\u50cd\u308b",
}


def filter_stray_furigana(candidates: list[str]) -> tuple[list[str], list[str]]:
    """Remove single-hiragana tokens that are adjacent to a kanji-containing token.

    Returns (kept, excluded) where *excluded* are the likely stray furigana.
    Multi-character hiragana words (する, いる, etc.) are never removed.
    """
    kept: list[str] = []
    excluded: list[str] = []
    n = len(candidates)
    for i, token in enumerate(candidates):
        if _SINGLE_HIRAGANA.match(token):
            prev_has_kanji = i > 0 and bool(_HAS_KANJI.search(candidates[i - 1]))
            next_has_kanji = i < n - 1 and bool(_HAS_KANJI.search(candidates[i + 1]))
            if prev_has_kanji or next_has_kanji:
                excluded.append(token)
                continue
        kept.append(token)
    return kept, excluded


def filter_tokens(tokens: list[str], known_words: set[str]) -> list[str]:
    return [token for token in tokens if token not in DEFAULT_PARTICLES and token not in known_words]
