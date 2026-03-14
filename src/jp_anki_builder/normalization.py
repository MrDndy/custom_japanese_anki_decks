from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

logger = logging.getLogger(__name__)

from jp_anki_builder.deinflect import deinflect
from jp_anki_builder.ocr_corrections import correct_with_dictionary as _ocr_correct
from jp_anki_builder.tokenize import (
    extract_candidate_token_sequence,
    extract_token_sequence,
    is_candidate_token,
)


@dataclass(frozen=True)
class NormalizedCandidate:
    surface: str
    lemma: str
    method: str
    confidence: float
    reason: str
    surface_chain: list[str] | None = None


class Normalizer(Protocol):
    def normalize_text(
        self,
        text: str,
        word_exists: Callable[[str], bool] | None = None,
    ) -> list[NormalizedCandidate]:
        ...


class RuleBasedNormalizer:
    method_name = "rule_based"

    def normalize_text(
        self,
        text: str,
        word_exists: Callable[[str], bool] | None = None,
    ) -> list[NormalizedCandidate]:
        surface_candidates = [token for token in extract_token_sequence(text) if is_candidate_token(token)]
        lemma_candidates = [token for token in extract_candidate_token_sequence(text) if is_candidate_token(token)]

        output: list[NormalizedCandidate] = []
        seen: set[str] = set()
        for idx, lemma in enumerate(lemma_candidates):
            surface = surface_candidates[idx] if idx < len(surface_candidates) else lemma
            chosen_lemma, confidence, reason = _choose_best_candidate(surface, lemma, word_exists)
            if chosen_lemma in seen:
                continue
            seen.add(chosen_lemma)
            output.append(
                NormalizedCandidate(
                    surface=surface,
                    lemma=chosen_lemma,
                    method=self.method_name,
                    confidence=confidence,
                    reason=reason,
                    surface_chain=[surface],
                )
            )
        return output


_MIZEN_TO_DICTIONARY_ENDING = {
    "か": "く",  # ? -> ?
    "が": "ぐ",  # ? -> ?
    "さ": "す",  # ? -> ?
    "た": "つ",  # ? -> ?
    "な": "ぬ",  # ? -> ?
    "ば": "ぶ",  # ? -> ?
    "ま": "む",  # ? -> ?
    "ら": "る",  # ? -> ?
    "わ": "う",  # ? -> ?
}

_POS_NOUN = "名詞"
_POS_VERB = "動詞"
_POS_AUX = "助動詞"


class SudachiNormalizer:
    method_name = "sudachi_nlp"

    def __init__(self) -> None:
        self._tokenizer = None
        self._decompose_cache: dict[str, list[str]] = {}

    def _get_tokenizer(self):
        if self._tokenizer is not None:
            return self._tokenizer
        try:
            from sudachipy import dictionary
        except ImportError as exc:
            raise RuntimeError(
                "NLP normalization requires sudachipy + sudachidict_core. "
                "Install with: .\\.venv312\\Scripts\\python -m pip install -e \".[japanese_nlp]\" "
                "and .\\.venv312\\Scripts\\python -m pip install sudachipy sudachidict_core."
            ) from exc
        self._tokenizer = dictionary.Dictionary().create()
        return self._tokenizer

    def normalize_text(
        self,
        text: str,
        word_exists: Callable[[str], bool] | None = None,
    ) -> list[NormalizedCandidate]:
        tokenizer = self._get_tokenizer()
        morphemes = [m for m in tokenizer.tokenize(text) if m.surface().strip()]

        output: list[NormalizedCandidate] = []
        seen: set[str] = set()

        def add_candidate(
            surface_text: str,
            lemma_text: str,
            confidence: float,
            reason: str,
            surface_chain: list[str] | None = None,
        ) -> None:
            if lemma_text in seen:
                return
            seen.add(lemma_text)
            output.append(
                NormalizedCandidate(
                    surface=surface_text,
                    lemma=lemma_text,
                    method=self.method_name,
                    confidence=confidence,
                    reason=reason,
                    surface_chain=surface_chain or [surface_text],
                )
            )
            for part in self._decompose_compound_lemma(lemma_text, word_exists):
                if part in seen:
                    continue
                seen.add(part)
                output.append(
                    NormalizedCandidate(
                        surface=part,
                        lemma=part,
                        method=self.method_name,
                        confidence=0.99,
                        reason="compound_decomposed",
                        surface_chain=[part],
                    )
                )

        i = 0
        while i < len(morphemes):
            current = morphemes[i]
            surface = current.surface()
            if not is_candidate_token(surface):
                i += 1
                continue

            pos1 = current.part_of_speech()[0]
            lemma = current.dictionary_form() or surface
            next_m = morphemes[i + 1] if i + 1 < len(morphemes) else None
            next2_m = morphemes[i + 2] if i + 2 < len(morphemes) else None

            reconstructed = _reconstruct_from_i_stem_sequence(current, next_m, next2_m)
            if reconstructed is not None:
                chain = [surface, next_m.surface(), next2_m.surface()]
                chain_surface = "".join(chain)
                chosen, confidence, reason = _choose_best_candidate(chain_surface, reconstructed, word_exists)
                add_candidate(chain_surface, chosen, confidence, reason, surface_chain=chain)
                i += 3
                while i < len(morphemes) and morphemes[i].part_of_speech()[0] == _POS_AUX:
                    i += 1
                continue

            if next_m is not None and next_m.part_of_speech()[0] == _POS_AUX:
                next_surface = next_m.surface()
                if next_surface in {"ず", "ぬ"}:
                    # Keep lexicalized negative compounds possible (e.g. ????).
                    compound = f"{surface}{next_surface}"
                    chosen, confidence, reason = _choose_best_candidate(compound, lemma, word_exists)
                    add_candidate(compound, chosen, confidence, reason, surface_chain=[surface, next_surface])
                    i += 2
                    continue

                if pos1 == _POS_VERB:
                    root = _sudachi_causative_passive_root(surface, next_surface)
                    if root is not None:
                        lemma = root
                    chain = [surface, next_surface]
                    chain_surface = "".join(chain)
                    chosen, confidence, reason = _choose_best_candidate(chain_surface, lemma, word_exists)
                    add_candidate(chain_surface, chosen, confidence, reason, surface_chain=chain)
                    i += 2
                    while i < len(morphemes) and morphemes[i].part_of_speech()[0] == _POS_AUX:
                        i += 1
                    continue

            chosen, confidence, reason = _choose_best_candidate(surface, lemma, word_exists)
            add_candidate(surface, chosen, confidence, reason, surface_chain=[surface])
            i += 1

        logger.debug("normalized %r -> %d candidate(s)", text, len(output))
        return output

    def _decompose_compound_lemma(
        self,
        lemma: str,
        word_exists: Callable[[str], bool] | None,
    ) -> list[str]:
        if not lemma or word_exists is None:
            return []
        if lemma in self._decompose_cache:
            return self._decompose_cache[lemma]

        try:
            from sudachipy import tokenizer as sudachi_tokenizer
        except Exception:
            self._decompose_cache[lemma] = []
            return []

        tokens = [
            m
            for m in self._get_tokenizer().tokenize(lemma, sudachi_tokenizer.Tokenizer.SplitMode.A)
            if m.surface().strip()
        ]
        if len(tokens) != 2:
            self._decompose_cache[lemma] = []
            return []

        left, right = tokens
        left_surface = left.surface()
        right_lemma = right.dictionary_form() or right.surface()
        if not (is_candidate_token(left_surface) and is_candidate_token(right_lemma)):
            self._decompose_cache[lemma] = []
            return []

        # Decompose only noun+verb compounds and only when both parts are known.
        if left.part_of_speech()[0] != _POS_NOUN or right.part_of_speech()[0] != _POS_VERB:
            self._decompose_cache[lemma] = []
            return []
        if not (word_exists(left_surface) and word_exists(right_lemma)):
            self._decompose_cache[lemma] = []
            return []

        parts = [left_surface, right_lemma]
        self._decompose_cache[lemma] = parts
        return parts


def _sudachi_causative_passive_root(surface: str, next_surface: str) -> str | None:
    if next_surface not in {"れる", "られる"}:
        return None
    if len(surface) < 2 or not surface.endswith("さ"):
        return None
    penultimate = surface[-2]
    mapped = _MIZEN_TO_DICTIONARY_ENDING.get(penultimate)
    if mapped is None:
        return None
    return f"{surface[:-2]}{mapped}"


def _reconstruct_from_i_stem_sequence(current, next_m, next2_m) -> str | None:
    # Sudachi may tokenize a godan-verb past/te form like:
    # ????? -> ??? (noun) + ? + ?
    if next_m is None or next2_m is None:
        return None
    if current.part_of_speech()[0] != _POS_NOUN:
        return None
    if next_m.surface() != "い":
        return None
    if next_m.part_of_speech()[0] != _POS_VERB:
        return None
    if next2_m.part_of_speech()[0] not in {_POS_AUX, "助詞"}:
        return None

    tail = next2_m.surface()
    if tail in {"た", "て"}:
        # ...?? / ...?? maps to godan-? dictionary forms.
        return f"{current.surface()}く"
    if tail in {"だ", "で"}:
        # ...?? / ...?? maps to godan-? dictionary forms.
        return f"{current.surface()}ぐ"
    return None


def _choose_best_candidate(
    surface: str,
    lemma: str,
    word_exists: Callable[[str], bool] | None,
) -> tuple[str, float, str]:
    if word_exists is None:
        if surface != lemma:
            return lemma, 0.95, "lemma_normalized"
        return lemma, 0.65, "surface_fallback"

    options: list[str] = []
    for candidate in (lemma, surface):
        if candidate and candidate not in options:
            options.append(candidate)
    for candidate in options:
        if word_exists(candidate):
            return candidate, 0.99, "dictionary_validated"

    # Deinflection fallback: when neither lemma nor surface validates,
    # try rule-based deinflection (Yomitan-style) to recover the
    # dictionary form from inflected/OCR-corrupted text.
    for base in (surface, lemma):
        for dc in deinflect(base)[1:]:  # skip original term
            if word_exists(dc.term):
                logger.debug(
                    "deinflection recovered %r -> %r via %s",
                    base, dc.term, " -> ".join(dc.reasons),
                )
                return dc.term, 0.97, "deinflection_validated"

    # OCR confusable correction: try substituting visually similar
    # characters (e.g. カ/力, ロ/口) and check against dictionary.
    for base in (surface, lemma):
        corrected = _ocr_correct(base, word_exists)
        if corrected is not None:
            logger.debug("OCR correction recovered %r -> %r", base, corrected)
            return corrected, 0.93, "ocr_corrected"

    if surface != lemma:
        return lemma, 0.95, "lemma_normalized"
    return lemma, 0.65, "surface_fallback"


_DEFAULT_NORMALIZER: Normalizer = SudachiNormalizer()


def get_default_normalizer() -> Normalizer:
    return _DEFAULT_NORMALIZER
