from __future__ import annotations

from jp_anki_builder import tokenize


def test_extract_candidates_uses_word_tokenizer_when_available(monkeypatch):
    monkeypatch.setattr(
        tokenize,
        "_build_word_tokenizer",
        lambda: (lambda text: ["冒険", "に", "行く", "勇者", "勇者"]),
    )

    result = tokenize.extract_candidates("ignored")
    assert result == ["冒険", "行く", "勇者"]


def test_extract_candidates_falls_back_to_regex_when_tokenizer_unavailable(monkeypatch):
    monkeypatch.setattr(tokenize, "_build_word_tokenizer", lambda: None)

    result = tokenize.extract_candidates("冒険に行く勇者")
    assert result == ["冒険に行く勇者"]
