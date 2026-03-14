"""Tests for the Yomitan-style deinflection engine."""

import pytest

from jp_anki_builder.deinflect import (
    DeinflectionCandidate,
    deinflect,
    deinflect_to_validated,
)


class TestDeinflect:
    """Core deinflection candidate generation."""

    def test_original_term_always_first(self):
        results = deinflect("食べる")
        assert results[0].term == "食べる"
        assert results[0].reasons == ()

    def test_empty_string_returns_empty(self):
        assert deinflect("") == []

    # --- Ichidan (v1) verbs ---

    def test_ichidan_te_form(self):
        terms = {c.term for c in deinflect("食べて")}
        assert "食べる" in terms

    def test_ichidan_ta_form(self):
        terms = {c.term for c in deinflect("食べた")}
        assert "食べる" in terms

    def test_ichidan_nai_form(self):
        terms = {c.term for c in deinflect("食べない")}
        assert "食べる" in terms

    def test_ichidan_masu_form(self):
        terms = {c.term for c in deinflect("食べます")}
        assert "食べる" in terms

    def test_ichidan_passive(self):
        terms = {c.term for c in deinflect("食べられる")}
        assert "食べる" in terms

    def test_ichidan_causative(self):
        terms = {c.term for c in deinflect("食べさせる")}
        assert "食べる" in terms

    def test_ichidan_conditional(self):
        terms = {c.term for c in deinflect("食べれば")}
        assert "食べる" in terms

    def test_ichidan_volitional(self):
        terms = {c.term for c in deinflect("食べよう")}
        assert "食べる" in terms

    def test_ichidan_imperative(self):
        terms = {c.term for c in deinflect("食べろ")}
        assert "食べる" in terms

    # --- Godan (v5) verbs ---

    def test_godan_ku_te_form(self):
        terms = {c.term for c in deinflect("書いて")}
        assert "書く" in terms

    def test_godan_mu_te_form(self):
        terms = {c.term for c in deinflect("飲んで")}
        assert "飲む" in terms

    def test_godan_su_te_form(self):
        terms = {c.term for c in deinflect("話して")}
        assert "話す" in terms

    def test_godan_u_past(self):
        terms = {c.term for c in deinflect("買った")}
        assert "買う" in terms

    def test_godan_tsu_past(self):
        terms = {c.term for c in deinflect("待った")}
        assert "待つ" in terms

    def test_godan_ru_past(self):
        """Godan-る verbs like 取る → 取った."""
        terms = {c.term for c in deinflect("取った")}
        assert "取る" in terms

    def test_godan_negative(self):
        terms = {c.term for c in deinflect("飲まない")}
        assert "飲む" in terms

    def test_godan_polite(self):
        terms = {c.term for c in deinflect("飲みます")}
        assert "飲む" in terms

    def test_godan_potential(self):
        terms = {c.term for c in deinflect("飲める")}
        assert "飲む" in terms

    def test_godan_passive(self):
        terms = {c.term for c in deinflect("飲まれる")}
        assert "飲む" in terms

    def test_godan_causative(self):
        terms = {c.term for c in deinflect("飲ませる")}
        assert "飲む" in terms

    def test_godan_conditional(self):
        terms = {c.term for c in deinflect("書けば")}
        assert "書く" in terms

    def test_godan_volitional(self):
        terms = {c.term for c in deinflect("飲もう")}
        assert "飲む" in terms

    def test_godan_imperative(self):
        terms = {c.term for c in deinflect("書け")}
        assert "書く" in terms

    # --- Special verbs ---

    def test_iku_special_te_form(self):
        """行く has irregular te-form 行って (not 行いて)."""
        terms = {c.term for c in deinflect("行って")}
        assert "行く" in terms

    def test_suru_past(self):
        terms = {c.term for c in deinflect("した")}
        assert "する" in terms

    def test_suru_te(self):
        terms = {c.term for c in deinflect("して")}
        assert "する" in terms

    def test_suru_negative(self):
        terms = {c.term for c in deinflect("しない")}
        assert "する" in terms

    def test_kuru_past(self):
        terms = {c.term for c in deinflect("きた")}
        assert "くる" in terms

    def test_kuru_negative(self):
        terms = {c.term for c in deinflect("こない")}
        assert "くる" in terms

    # --- i-adjectives ---

    def test_adj_negative(self):
        terms = {c.term for c in deinflect("美しくない")}
        assert "美しい" in terms

    def test_adj_past(self):
        terms = {c.term for c in deinflect("美しかった")}
        assert "美しい" in terms

    def test_adj_te(self):
        terms = {c.term for c in deinflect("美しくて")}
        assert "美しい" in terms

    def test_adj_adverbial(self):
        terms = {c.term for c in deinflect("美しく")}
        assert "美しい" in terms

    def test_adj_conditional(self):
        terms = {c.term for c in deinflect("美しければ")}
        assert "美しい" in terms

    # --- Chained deinflection ---

    def test_negative_past_chain(self):
        """食べなかった → 食べない → 食べる (two-step chain)."""
        terms = {c.term for c in deinflect("食べなかった")}
        assert "食べる" in terms

    def test_polite_negative(self):
        terms = {c.term for c in deinflect("食べません")}
        assert "食べる" in terms

    def test_polite_past(self):
        terms = {c.term for c in deinflect("食べました")}
        assert "食べる" in terms

    # --- te-iru forms ---

    def test_te_iru(self):
        terms = {c.term for c in deinflect("食べている")}
        assert "食べる" in terms

    def test_te_ru_contraction(self):
        terms = {c.term for c in deinflect("食べてる")}
        assert "食べる" in terms


class TestDeinflectToValidated:
    """Dictionary-validated deinflection."""

    def _make_dict(self, words: set[str]):
        return lambda w: w in words

    def test_finds_validated_form(self):
        word_exists = self._make_dict({"飲む", "食べる"})
        assert deinflect_to_validated("飲んで", word_exists) == "飲む"

    def test_returns_none_when_no_match(self):
        word_exists = self._make_dict(set())
        assert deinflect_to_validated("飲んで", word_exists) is None

    def test_skips_original_term(self):
        """Should not return the original term even if it's in the dictionary."""
        word_exists = self._make_dict({"飲んで"})
        assert deinflect_to_validated("飲んで", word_exists) is None

    def test_adj_negative_past(self):
        word_exists = self._make_dict({"痛い"})
        assert deinflect_to_validated("痛くなかった", word_exists) == "痛い"

    def test_compound_suru(self):
        word_exists = self._make_dict({"勉強する"})
        assert deinflect_to_validated("勉強して", word_exists) == "勉強する"


class TestNormalizationIntegration:
    """Test that deinflection integrates into the normalization pipeline."""

    def test_choose_best_candidate_uses_deinflection(self):
        from jp_anki_builder.normalization import _choose_best_candidate

        word_exists = lambda w: w in {"飲む"}
        # Surface is inflected, lemma is also wrong/missing
        result, confidence, reason = _choose_best_candidate("飲んで", "飲んで", word_exists)
        assert result == "飲む"
        assert reason == "deinflection_validated"
        assert confidence == 0.97

    def test_dictionary_validated_takes_precedence(self):
        from jp_anki_builder.normalization import _choose_best_candidate

        word_exists = lambda w: w in {"飲む", "飲んで"}
        # When surface or lemma validates directly, deinflection is not used
        result, confidence, reason = _choose_best_candidate("飲んで", "飲む", word_exists)
        assert result == "飲む"
        assert reason == "dictionary_validated"
        assert confidence == 0.99
