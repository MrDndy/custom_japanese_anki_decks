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

    **Thread safety:** This class is NOT thread-safe. A single instance must be
    constructed and used exclusively from one thread. In the real-time overlay,
    construct this inside the NLP worker's ``run()`` method — not on the main
    thread — so that every call to ``lookup()`` comes from the same thread that
    created the underlying SudachiPy tokenizer and dictionary objects.
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
        """Normalize → filter particles/SFX → lookup each word → return results.

        Results are sorted by proximity to the center of *text*, so the word
        under the cursor (which sits at the center of the captured ROI) appears
        first in the list.
        """
        start = time.monotonic()

        candidates = self._normalizer.normalize_text(
            text, word_exists=self._word_exists.word_exists
        )

        results: list[LookupResult] = []
        # Track each result's position in the original text for center-ranking.
        result_positions: list[int] = []
        text_center = len(text) / 2

        search_offset = 0
        for cand in candidates:
            lemma = cand.lemma
            surface = cand.surface

            # Record position of this surface in the original text.
            pos_in_text = text.find(surface, search_offset)
            if pos_in_text >= 0:
                search_offset = pos_in_text + len(surface)
            else:
                # Fallback: try from the start
                pos_in_text = text.find(surface)
                if pos_in_text < 0:
                    pos_in_text = search_offset  # best guess

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
            # Distance from center of the surface's midpoint
            surface_mid = pos_in_text + len(surface) / 2
            result_positions.append(abs(surface_mid - text_center))

        # Sort results so the word closest to the center of the text comes first.
        if result_positions:
            paired = sorted(zip(result_positions, results), key=lambda p: p[0])
            results = [r for _, r in paired]

        elapsed_ms = (time.monotonic() - start) * 1000
        return TextLookupResponse(
            raw_text=text,
            words=results,
            processing_time_ms=elapsed_ms,
        )

    def _get_pos(self, word: str) -> str:
        """Return the first part-of-speech tag for *word* from Sudachi."""
        return self._normalizer.get_pos(word)

    def _is_in_vocab_db(self, expression: str) -> bool:
        return self._vocab_db.has_expression(expression)

    def close(self) -> None:
        self._vocab_db.close()

    def __enter__(self) -> LookupService:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()
