from __future__ import annotations

from dataclasses import dataclass
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
    def normalize_text(self, text: str) -> list[NormalizedCandidate]:
        ...


class RuleBasedNormalizer:
    method_name = "rule_based"

    def normalize_text(self, text: str) -> list[NormalizedCandidate]:
        surface_candidates = [token for token in extract_token_sequence(text) if is_candidate_token(token)]
        lemma_candidates = [token for token in extract_candidate_token_sequence(text) if is_candidate_token(token)]

        output: list[NormalizedCandidate] = []
        seen: set[str] = set()
        for idx, lemma in enumerate(lemma_candidates):
            if lemma in seen:
                continue
            seen.add(lemma)
            surface = surface_candidates[idx] if idx < len(surface_candidates) else lemma
            changed = surface != lemma
            output.append(
                NormalizedCandidate(
                    surface=surface,
                    lemma=lemma,
                    method=self.method_name,
                    confidence=0.95 if changed else 0.65,
                    reason="lemma_normalized" if changed else "surface_fallback",
                )
            )
        return output


_DEFAULT_NORMALIZER: Normalizer = RuleBasedNormalizer()


def get_default_normalizer() -> Normalizer:
    return _DEFAULT_NORMALIZER
