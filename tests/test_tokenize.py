from __future__ import annotations

from jp_anki_builder import tokenize


def test_extract_candidates_uses_word_tokenizer_when_available(monkeypatch):
    monkeypatch.setattr(
        tokenize,
        "_build_word_tokenizer",
        lambda: (lambda text: ["\u5192\u967a", "\u306b", "\u884c\u304f", "\u52c7\u8005", "\u52c7\u8005"]),
    )

    result = tokenize.extract_candidates("ignored")
    assert result == ["\u5192\u967a", "\u884c\u304f", "\u52c7\u8005"]


def test_extract_candidates_falls_back_to_regex_when_tokenizer_unavailable(monkeypatch):
    monkeypatch.setattr(tokenize, "_build_word_tokenizer", lambda: None)

    result = tokenize.extract_candidates("\u5192\u967a\u306b\u884c\u304f\u52c7\u8005")
    assert result == ["\u5192\u967a", "\u884c\u304f\u52c7\u8005"]


def test_extract_candidates_fallback_splits_particle_sentence(monkeypatch):
    monkeypatch.setattr(tokenize, "_build_word_tokenizer", lambda: None)

    result = tokenize.extract_candidates("\u8db3\u304c\u75db\u3044")
    assert result == ["\u8db3", "\u75db\u3044"]


def test_extract_candidates_augments_i_adjective_from_ocr_noise(monkeypatch):
    monkeypatch.setattr(
        tokenize,
        "_build_word_tokenizer",
        lambda: (lambda text: ["\u75db", "\u3082", "\u3044"]),
    )

    result = tokenize.extract_candidates("ignored")
    assert "\u75db\u3044" in result
