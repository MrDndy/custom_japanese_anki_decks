from __future__ import annotations

from jp_anki_builder.normalization import RuleBasedNormalizer


def test_rule_based_normalizer_returns_structured_entries():
    normalizer = RuleBasedNormalizer()

    result = normalizer.normalize_text("弱かった")

    assert result
    first = result[0]
    assert first.surface
    assert first.lemma
    assert first.method == "rule_based"
    assert isinstance(first.confidence, float)
    assert first.reason in {"lemma_normalized", "surface_fallback"}


def test_rule_based_normalizer_keeps_current_verb_regressions_fixed():
    normalizer = RuleBasedNormalizer()

    lemmas = [entry.lemma for entry in normalizer.normalize_text("奪われる 歩かされる")]
    assert "奪う" in lemmas
    assert "歩く" in lemmas
