from __future__ import annotations

from jp_anki_builder import tokenize


def test_extract_candidates_uses_word_tokenizer_when_available(monkeypatch):
    monkeypatch.setattr(tokenize, "extract_candidate_token_sequence", lambda text: ["冒険", "に", "行く", "勇者", "勇者"])

    result = tokenize.extract_candidates("ignored")
    assert result == ["冒険", "行く", "勇者"]


def test_extract_candidates_falls_back_to_regex_when_tokenizer_unavailable(monkeypatch):
    monkeypatch.setattr(tokenize, "extract_candidate_token_sequence", lambda text: ["冒険", "に", "行く", "勇者"])

    result = tokenize.extract_candidates("冒険に行く勇者")
    assert result == ["冒険", "行く", "勇者"]


def test_extract_candidates_fallback_splits_particle_sentence(monkeypatch):
    monkeypatch.setattr(tokenize, "extract_candidate_token_sequence", lambda text: ["足", "が", "痛い"])

    result = tokenize.extract_candidates("足が痛い")
    assert result == ["足", "痛い"]


def test_extract_candidates_augments_i_adjective_from_ocr_noise(monkeypatch):
    monkeypatch.setattr(tokenize, "extract_candidate_token_sequence", lambda text: ["痛", "も", "い"])

    result = tokenize.extract_candidates("ignored")
    assert "痛い" in result


def test_extract_candidates_keeps_dictionary_form_from_tokenizer(monkeypatch):
    monkeypatch.setattr(tokenize, "extract_candidate_token_sequence", lambda text: ["弱い", "焼く", "は"])

    result = tokenize.extract_candidates("ignored")
    assert result == ["弱い", "焼く"]


class _Feature:
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)


class _Word:
    def __init__(self, surface: str, feature: _Feature):
        self.surface = surface
        self.feature = feature


def test_word_dictionary_form_only_for_renyoukei_inflection():
    renyou = _Word(
        "焼い",
        _Feature(pos1="動詞", cType="五段-カ行", cForm="連用形-イ音便", lemma="焼く"),
    )
    mizen = _Word(
        "役立た",
        _Feature(pos1="動詞", cType="五段-タ行", cForm="未然形-一般", lemma="役立つ"),
    )
    suffix = _Word(
        "ら",
        _Feature(pos1="接尾辞", cType="*", cForm="*", lemma="等"),
    )

    assert tokenize._word_dictionary_form(renyou) == "焼く"
    assert tokenize._word_dictionary_form(mizen) is None
    assert tokenize._word_dictionary_form(suffix) is None


def test_word_dictionary_form_supports_adjective_and_ichidan_renyoukei():
    adj = _Word(
        "弱かっ",
        _Feature(pos1="形容詞", cType="形容詞", cForm="連用形-促音便", lemma="弱い"),
    )
    ichidan = _Word(
        "仕留め",
        _Feature(pos1="動詞", cType="一段", cForm="連用形-一般", lemma="仕留める"),
    )
    assert tokenize._word_dictionary_form(adj) == "弱い"
    assert tokenize._word_dictionary_form(ichidan) == "仕留める"


def test_word_dictionary_form_supports_renyoukei_auxiliary_like_yagaru():
    aux = _Word(
        "やがっ",
        _Feature(pos1="助動詞", cType="五段-ラ行", cForm="連用形-促音便", lemma="やがる"),
    )
    assert tokenize._word_dictionary_form(aux) == "やがる"


def test_is_negative_aux_pair_detects_verb_plus_zu():
    left = _Word("役立た", _Feature(pos1="動詞", cForm="未然形-一般"))
    right = _Word("ず", _Feature(pos1="助動詞"))
    assert tokenize._is_negative_aux_pair(left, right) is True

def test_extract_candidates_normalizes_mizen_plus_aux_chain_to_dictionary_form():
    assert tokenize.extract_candidates("\u596a\u308f\u308c\u308b") == ["\u596a\u3046"]


def test_extract_candidate_sequence_keeps_negative_lexicalized_compound():
    assert "\u5f79\u7acb\u305f\u305a" in tokenize.extract_candidate_token_sequence(
        "\u5f79\u7acb\u305f\u305a\u304b\u3002"
    )


def test_extract_candidates_normalizes_causative_passive_to_root_dictionary_form():
    assert tokenize.extract_candidates("\u6b69\u304b\u3055\u308c\u308b") == ["\u6b69\u304f"]


def test_extract_candidates_normalizes_another_causative_passive_to_root():
    assert tokenize.extract_candidates("\u8aad\u307e\u3055\u308c\u308b") == ["\u8aad\u3080"]
