from __future__ import annotations

from jp_anki_builder import normalization
from jp_anki_builder.normalization import RuleBasedNormalizer, SudachiNormalizer, get_default_normalizer


def test_default_normalizer_is_sudachi_nlp():
    normalizer_obj = get_default_normalizer()
    assert isinstance(normalizer_obj, SudachiNormalizer)
    assert normalizer_obj.method_name == "sudachi_nlp"


def test_sudachi_normalizer_keeps_current_verb_regressions_fixed():
    normalizer_obj = SudachiNormalizer()

    lemmas = [entry.lemma for entry in normalizer_obj.normalize_text("\u596a\u308f\u308c\u308b \u6b69\u304b\u3055\u308c\u308b")]
    assert "\u596a\u3046" in lemmas
    assert "\u6b69\u304f" in lemmas


def test_sudachi_normalizer_reconstructs_kana_i_stem_past_to_dictionary_form():
    normalizer_obj = SudachiNormalizer()

    result = normalizer_obj.normalize_text("\u304f\u3058\u5f15\u3044\u305f", word_exists=lambda w: w == "\u304f\u3058\u5f15\u304f")
    lemmas = [entry.lemma for entry in result]
    assert "\u304f\u3058\u5f15\u304f" in lemmas


def test_sudachi_normalizer_reconstructs_kana_i_stem_without_dictionary_hit():
    normalizer_obj = SudachiNormalizer()

    result = normalizer_obj.normalize_text("\u304f\u3058\u5f15\u3044\u305f", word_exists=lambda w: False)
    target = next(entry for entry in result if entry.lemma == "\u304f\u3058\u5f15\u304f")
    assert target.surface == "\u304f\u3058\u5f15\u3044\u305f"
    assert target.surface_chain == ["\u304f\u3058\u5f15", "\u3044", "\u305f"]


def test_sudachi_normalizer_decomposes_compound_verb_when_parts_are_dictionary_backed():
    normalizer_obj = SudachiNormalizer()
    known = {"\u304f\u3058", "\u5f15\u304f"}
    result = normalizer_obj.normalize_text("\u304f\u3058\u5f15\u3044\u305f", word_exists=lambda w: w in known)
    lemmas = [entry.lemma for entry in result]
    assert "\u304f\u3058" in lemmas
    assert "\u5f15\u304f" in lemmas


def test_rule_based_normalizer_prefers_dictionary_validated_option(monkeypatch):
    normalizer_obj = RuleBasedNormalizer()
    monkeypatch.setattr(normalization, "extract_token_sequence", lambda text: ["\u5f79\u7acb\u305f\u305a"])
    monkeypatch.setattr(normalization, "extract_candidate_token_sequence", lambda text: ["\u5f79\u7acb\u3064"])
    monkeypatch.setattr(normalization, "is_candidate_token", lambda token: True)

    result = normalizer_obj.normalize_text("\u5f79\u7acb\u305f\u305a", word_exists=lambda word: word == "\u5f79\u7acb\u305f\u305a")

    assert result[0].lemma == "\u5f79\u7acb\u305f\u305a"
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
