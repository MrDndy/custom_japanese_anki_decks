from __future__ import annotations

import re
from collections.abc import Callable


JAPANESE_CHUNK_RE = re.compile(r"[\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff]+")
HAS_JAPANESE_RE = re.compile(r"[\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff]")
HAS_KANJI_KATA_RE = re.compile(r"[\u30a0-\u30ff\u3400-\u4dbf\u4e00-\u9fff]")
IS_HIRAGANA_RE = re.compile(r"^[\u3040-\u309f]+$")
PARTICLES = {"は", "が", "を", "に", "で", "と", "も", "の", "へ", "か"}


def _build_word_tokenizer() -> Callable[[str], list[str]] | None:
    try:
        import fugashi
    except ImportError:
        return None

    tagger = fugashi.Tagger()

    def tokenize(text: str) -> list[str]:
        words = list(tagger(text))
        tokens: list[str] = []
        i = 0
        while i < len(words):
            word = words[i]
            surface = word.surface
            if i + 1 < len(words):
                nxt = words[i + 1]
                if _is_negative_aux_pair(word, nxt):
                    # Keep lexicalized negative compounds possible (e.g. 役立たず)
                    # and avoid standalone stem artifacts.
                    tokens.append(surface + nxt.surface)
                    i += 2
                    continue
            lemma = _word_dictionary_form(word)
            tokens.append(lemma or surface)
            i += 1
        return tokens

    return tokenize


def _word_dictionary_form(word) -> str | None:
    feature = getattr(word, "feature", None)
    if feature is None:
        return None
    pos1 = _feature_value(feature, "pos1")
    ctype = _feature_value(feature, "cType")
    cform = _feature_value(feature, "cForm")

    if pos1 not in {"動詞", "形容詞", "助動詞"}:
        return None
    if not ctype or ctype == "*":
        return None
    # Restrict normalization to renyoukei-like inflections to reduce false lemma shifts
    # like ウチら -> 等 and 役立たず -> 役立つ.
    if not cform or not str(cform).startswith("連用形"):
        return None

    for attr in ("lemma", "dictionary_form", "base_form", "lemma_form"):
        value = _feature_value(feature, attr)
        if isinstance(value, str) and value and value != "*":
            return value
    return None


def _feature_value(feature, attr: str):
    return getattr(feature, attr, None)


def _is_negative_aux_pair(word, next_word) -> bool:
    feature = getattr(word, "feature", None)
    next_feature = getattr(next_word, "feature", None)
    if feature is None or next_feature is None:
        return False
    return (
        _feature_value(feature, "pos1") == "動詞"
        and _feature_value(feature, "cForm") is not None
        and str(_feature_value(feature, "cForm")).startswith("未然形")
        and _feature_value(next_feature, "pos1") == "助動詞"
        and next_word.surface in {"ず", "ぬ"}
    )


def _regex_tokenize(text: str) -> list[str]:
    chunks = JAPANESE_CHUNK_RE.findall(text)
    tokens: list[str] = []
    for chunk in chunks:
        tokens.extend(_split_chunk_on_particles(chunk))
    return tokens


def _split_chunk_on_particles(chunk: str) -> list[str]:
    # Fallback segmentation when morphological tokenizer deps are unavailable.
    # Example: 足が痛い -> 足, が, 痛い
    out: list[str] = []
    buf = ""
    for ch in chunk:
        if ch in PARTICLES:
            if buf:
                out.append(buf)
                buf = ""
            out.append(ch)
        else:
            buf += ch
    if buf:
        out.append(buf)
    return out


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


def is_candidate_token(token: str) -> bool:
    return _is_candidate_token(token)


def extract_candidates(text: str) -> list[str]:
    raw_tokens = extract_candidate_token_sequence(text)
    raw_tokens = _augment_noise_corrected_tokens(raw_tokens)

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


def extract_token_sequence(text: str) -> list[str]:
    tokenizer = _build_surface_tokenizer()
    return tokenizer(text) if tokenizer else _regex_tokenize(text)


def extract_candidate_token_sequence(text: str) -> list[str]:
    tokenizer = _build_word_tokenizer()
    return tokenizer(text) if tokenizer else _regex_tokenize(text)


def _build_surface_tokenizer() -> Callable[[str], list[str]] | None:
    try:
        import fugashi
    except ImportError:
        return None

    tagger = fugashi.Tagger()

    def tokenize(text: str) -> list[str]:
        return [word.surface for word in tagger(text)]

    return tokenize


def _augment_noise_corrected_tokens(tokens: list[str]) -> list[str]:
    # OCR sometimes inserts a stray single-particle hiragana inside i-adjectives:
    # e.g. 痛もい -> 痛, も, い. Add corrected form 痛い as an extra candidate.
    if len(tokens) < 3:
        return tokens

    augmented = list(tokens)
    for i in range(len(tokens) - 2):
        a, b, c = tokens[i], tokens[i + 1], tokens[i + 2]
        if (
            len(a) >= 1
            and HAS_KANJI_KATA_RE.search(a)
            and b in PARTICLES
            and c == "い"
        ):
            augmented.append(f"{a}い")
    return augmented
