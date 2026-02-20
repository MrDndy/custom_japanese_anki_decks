from __future__ import annotations

from jp_anki_builder import normalization
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


def test_rule_based_normalizer_prefers_dictionary_validated_option(monkeypatch):
    normalizer_obj = RuleBasedNormalizer()
    monkeypatch.setattr(normalization, "extract_token_sequence", lambda text: ["役立たず"])
    monkeypatch.setattr(normalization, "extract_candidate_token_sequence", lambda text: ["役立つ"])
    monkeypatch.setattr(normalization, "is_candidate_token", lambda token: True)

    result = normalizer_obj.normalize_text("役立たず", word_exists=lambda word: word == "役立たず")

    assert result[0].lemma == "役立たず"
    assert result[0].reason == "dictionary_validated"

def test_rule_based_normalizer_uses_lemma_normalized_when_dictionary_has_no_hit(monkeypatch):
    normalizer_obj = RuleBasedNormalizer()
    monkeypatch.setattr(normalization, "extract_token_sequence", lambda text: ["\u596a\u308f"])
    monkeypatch.setattr(normalization, "extract_candidate_token_sequence", lambda text: ["\u596a\u3046"])
    monkeypatch.setattr(normalization, "is_candidate_token", lambda token: True)

    result = normalizer_obj.normalize_text("\u596a\u308f\u308c\u308b", word_exists=lambda word: False)

    assert result[0].lemma == "\u596a\u3046"
    assert result[0].reason == "lemma_normalized"


def test_rule_based_normalizer_uses_surface_fallback_when_no_lemma_change(monkeypatch):
    normalizer_obj = RuleBasedNormalizer()
    monkeypatch.setattr(normalization, "extract_token_sequence", lambda text: ["\u5192\u967a"])
    monkeypatch.setattr(normalization, "extract_candidate_token_sequence", lambda text: ["\u5192\u967a"])
    monkeypatch.setattr(normalization, "is_candidate_token", lambda token: True)

    result = normalizer_obj.normalize_text("\u5192\u967a", word_exists=lambda word: False)

    assert result[0].lemma == "\u5192\u967a"
    assert result[0].reason == "surface_fallback"
