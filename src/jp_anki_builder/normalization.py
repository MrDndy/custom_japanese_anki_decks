from __future__ import annotations

from dataclasses import dataclass
from collections.abc import Callable
from typing import Protocol

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
                )
            )
        return output


def _choose_best_candidate(
    surface: str,
    lemma: str,
    word_exists: Callable[[str], bool] | None,
) -> tuple[str, float, str]:
    if word_exists is None:
        if surface != lemma:
            return lemma, 0.95, "lemma_normalized"
        return lemma, 0.65, "surface_fallback"

    options = []
    for candidate in (lemma, surface):
        if candidate and candidate not in options:
            options.append(candidate)
    for candidate in options:
        if word_exists(candidate):
            return candidate, 0.99, "dictionary_validated"
    if surface != lemma:
        return lemma, 0.95, "lemma_normalized"
    return lemma, 0.65, "surface_fallback"


_DEFAULT_NORMALIZER: Normalizer = RuleBasedNormalizer()


def get_default_normalizer() -> Normalizer:
    return _DEFAULT_NORMALIZER
