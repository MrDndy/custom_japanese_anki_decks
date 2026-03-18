from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from jp_anki_builder.lookup_service import LookupResult

logger = logging.getLogger(__name__)

# Type alias — avoids a hard import at module level.
_AnkiConnectClientType = object  # runtime: AnkiConnectClient | None


@dataclass
class SessionWord:
    surface: str
    dictionary_form: str
    reading: str
    meanings: list[str]
    jlpt_level: str
    added_at: str         # ISO datetime
    source_context: str   # full OCR text where this word was found


class SessionBuffer:
    """Accumulates words during a real-time session and exports to Anki deck.

    Dedup within session: same ``(dictionary_form, reading)`` pair is only
    added once.  Export reuses the same genanki model/template as the batch
    pipeline so cards are compatible across workflows.
    """

    def __init__(
        self,
        data_dir: str = "data",
        anki_client: _AnkiConnectClientType | None = None,
    ) -> None:
        self._data_dir = data_dir
        self._anki_client = anki_client  # optional AnkiConnectClient for live dedup
        self._words: list[SessionWord] = []
        self._seen_forms: set[tuple[str, str]] = set()

    def add_word(self, result: LookupResult, source_text: str) -> bool:
        """Add a word to the buffer.  Returns False if duplicate.

        If an ``AnkiConnectClient`` was supplied at construction and Anki is
        running, the word is also skipped when it already exists in the user's
        collection (``can_add_note()`` returns False).
        """
        key = (result.dictionary_form, result.reading)
        if key in self._seen_forms:
            return False
        # Optional live dedup against the user's Anki collection.
        if self._anki_client is not None:
            try:
                if not self._anki_client.can_add_note(
                    deck="",
                    expression=result.dictionary_form,
                    reading=result.reading,
                ):
                    logger.debug(
                        "skipping %r — already in Anki collection",
                        result.dictionary_form,
                    )
                    return False
            except Exception as exc:
                logger.warning("AnkiConnect dedup check failed: %s", exc)
        self._seen_forms.add(key)
        self._words.append(
            SessionWord(
                surface=result.surface,
                dictionary_form=result.dictionary_form,
                reading=result.reading,
                meanings=list(result.meanings),
                jlpt_level=result.jlpt_level,
                added_at=datetime.now().isoformat(),
                source_context=source_text,
            )
        )
        return True

    def remove_word(self, index: int) -> None:
        """Remove a word by index."""
        if 0 <= index < len(self._words):
            word = self._words.pop(index)
            self._seen_forms.discard((word.dictionary_form, word.reading))

    def get_words(self) -> list[SessionWord]:
        """Get all buffered words."""
        return list(self._words)

    def __len__(self) -> int:
        return len(self._words)

    def export_deck(
        self,
        deck_name: str,
        volume: str | None = None,
        chapter: str | None = None,
    ) -> Path:
        """Generate an Anki deck from the buffer using the existing build pipeline.

        Returns the path to the generated ``.apkg`` file.
        """
        if not self._words:
            raise ValueError("Cannot export an empty session buffer")

        try:
            import genanki
        except ImportError as exc:
            raise RuntimeError(
                "export_deck requires 'genanki'. "
                "Install with: pip install genanki"
            ) from exc

        from jp_anki_builder.build import _deck_id, _model_id
        from jp_anki_builder.cards import build_deck_name, build_genanki_model, build_note_fields
        from jp_anki_builder.vocab_db import VocabDB

        full_deck_name = build_deck_name(
            source=deck_name, volume=volume, chapter=chapter
        )

        model = build_genanki_model(_model_id())
        deck = genanki.Deck(_deck_id(full_deck_name), full_deck_name)

        for word in self._words:
            if not word.meanings:
                continue
            note = build_note_fields(
                word=word.dictionary_form,
                reading=word.reading,
                meanings=word.meanings,
            )
            deck.add_note(
                genanki.Note(
                    model=model,
                    fields=[note["kanji"], note["reading"], note["meaning"]],
                    guid=genanki.guid_for(full_deck_name, note["kanji"]),
                )
            )

        output_dir = Path(self._data_dir) / "realtime_sessions"
        output_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = output_dir / f"{deck_name}_{timestamp}.apkg"

        package = genanki.Package(deck)
        package.write_to_file(str(output_path))
        logger.info("exported %d card(s) to %s", len(self._words), output_path)

        # Record to central vocabulary database.
        vocab_db_path = Path(self._data_dir) / "vocabulary.db"
        with VocabDB(vocab_db_path) as vocab_db:
            vocab_db.record_exports(
                [
                    {"word": w.dictionary_form, "reading": w.reading}
                    for w in self._words
                ],
                deck_name=full_deck_name,
                source="realtime",
            )

        return output_path

    def clear(self) -> None:
        """Clear the buffer."""
        self._words.clear()
        self._seen_forms.clear()
