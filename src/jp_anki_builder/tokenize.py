from __future__ import annotations

import re
from collections.abc import Callable


JAPANESE_CHUNK_RE = re.compile(r"[\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff]+")
HAS_JAPANESE_RE = re.compile(r"[\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff]")
HAS_KANJI_KATA_RE = re.compile(r"[\u30a0-\u30ff\u3400-\u4dbf\u4e00-\u9fff]")
IS_HIRAGANA_RE = re.compile(r"^[\u3040-\u309f]+$")


def _build_word_tokenizer() -> Callable[[str], list[str]] | None:
    try:
        import fugashi
    except ImportError:
        return None

    tagger = fugashi.Tagger()

    def tokenize(text: str) -> list[str]:
        return [word.surface for word in tagger(text)]

    return tokenize


def _regex_tokenize(text: str) -> list[str]:
    return JAPANESE_CHUNK_RE.findall(text)


def _is_candidate_token(token: str) -> bool:
    cleaned = token.strip()
    if not cleaned:
        return False
    if not HAS_JAPANESE_RE.search(cleaned):
        return False
    if HAS_KANJI_KATA_RE.search(cleaned):
        return True
    # Pure hiragana words are often particles/noise when length 1.
    if IS_HIRAGANA_RE.match(cleaned):
        return len(cleaned) >= 2
    return True


def extract_candidates(text: str) -> list[str]:
    tokenizer = _build_word_tokenizer()
    raw_tokens = tokenizer(text) if tokenizer else _regex_tokenize(text)

    seen: set[str] = set()
    result: list[str] = []
    for token in raw_tokens:
        if not _is_candidate_token(token):
            continue
        if token in seen:
            continue
        seen.add(token)
        result.append(token)
    return result
