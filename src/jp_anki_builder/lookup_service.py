from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from pathlib import Path

from jp_anki_builder.dictionary import (
    WordExistsCache,
    build_offline_dictionary,
    build_online_dictionary,
)
from jp_anki_builder.enrich import enrich_word
from jp_anki_builder.filtering import DEFAULT_PARTICLES, is_sfx_token
from jp_anki_builder.jlpt import build_jlpt_lookup
from jp_anki_builder.normalization import SudachiNormalizer
from jp_anki_builder.vocab_db import VocabDB

logger = logging.getLogger(__name__)


@dataclass
class LookupResult:
    surface: str
    dictionary_form: str
    reading: str
    meanings: list[str]
    part_of_speech: str
    confidence: float
    jlpt_level: str
    is_in_vocab_db: bool


@dataclass
class TextLookupResponse:
    raw_text: str
    words: list[LookupResult]
    processing_time_ms: float


class LookupService:
    """Stateful service that tokenizes, normalizes, and looks up Japanese text.

    Wraps the existing normalization + dictionary + JLPT pipeline into a single
    call suitable for real-time use. Pre-warms models on init.
    """

    def __init__(self, data_dir: str = "data", online_dict: str = "off") -> None:
        self._normalizer = SudachiNormalizer()
        self._offline = build_offline_dictionary(data_dir)
        self._online = build_online_dictionary(online_dict)
        self._word_exists = WordExistsCache(self._offline, self._online)
        self._jlpt = build_jlpt_lookup(data_dir)
        db_path = Path(data_dir) / "vocabulary.db"
        self._vocab_db = VocabDB(db_path)
        # Pre-warm the SudachiPy tokenizer so the first real lookup is fast.
        try:
            self._normalizer.normalize_text("日本語")
        except Exception:
            pass

    def lookup(self, text: str) -> TextLookupResponse:
        """Normalize → filter particles/SFX → lookup each word → return results."""
        start = time.monotonic()

        candidates = self._normalizer.normalize_text(
            text, word_exists=self._word_exists.word_exists
        )

        results: list[LookupResult] = []
        for cand in candidates:
            lemma = cand.lemma
            surface = cand.surface

            # Filter particles and common stop-words
            if lemma in DEFAULT_PARTICLES or surface in DEFAULT_PARTICLES:
                continue

            # Filter SFX / onomatopoeia
            if is_sfx_token(lemma, self._word_exists.word_exists):
                continue

            entry = enrich_word(lemma, self._offline, self._online, max_meanings=3)
            pos = self._get_pos(lemma)
            in_db = self._is_in_vocab_db(lemma)

            results.append(
                LookupResult(
                    surface=surface,
                    dictionary_form=lemma,
                    reading=entry.get("reading", ""),
                    meanings=entry.get("meanings", []),
                    part_of_speech=pos,
                    confidence=cand.confidence,
                    jlpt_level=self._jlpt.level_tag(lemma),
                    is_in_vocab_db=in_db,
                )
            )

        elapsed_ms = (time.monotonic() - start) * 1000
        return TextLookupResponse(
            raw_text=text,
            words=results,
            processing_time_ms=elapsed_ms,
        )

    def _get_pos(self, word: str) -> str:
        """Return the first part-of-speech tag for *word* from Sudachi."""
        try:
            tokenizer = self._normalizer._get_tokenizer()
            morphemes = tokenizer.tokenize(word)
            if morphemes:
                return morphemes[0].part_of_speech()[0]
        except Exception:
            pass
        return ""

    def _is_in_vocab_db(self, expression: str) -> bool:
        try:
            row = self._vocab_db._conn.execute(
                "SELECT id FROM vocabulary WHERE expression = ?",
                (expression,),
            ).fetchone()
            return row is not None
        except Exception:
            return False

    def close(self) -> None:
        self._vocab_db.close()

    def __enter__(self) -> LookupService:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()
