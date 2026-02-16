from __future__ import annotations

import json
import random
from dataclasses import dataclass
from pathlib import Path

from jp_anki_builder.cards import build_bidirectional_fields, build_deck_name
from jp_anki_builder.config import RunPaths
from jp_anki_builder.dictionary import NullOnlineDictionary, OfflineJsonDictionary
from jp_anki_builder.enrich import enrich_word


@dataclass
class BuildSummary:
    run_id: str
    source: str
    note_count: int
    package_path: str
    artifact_path: str


def _stable_id(seed_text: str) -> int:
    random.seed(seed_text)
    return random.randint(1_000_000_000, 2_000_000_000)


def run_build(
    source: str,
    run_id: str,
    base_dir: str = "data",
    volume: str | None = None,
    chapter: str | None = None,
) -> BuildSummary:
    paths = RunPaths(base_dir=base_dir, source_id=source, run_id=run_id)
    if not paths.review_artifact.exists():
        raise ValueError(f"review artifact not found: {paths.review_artifact}")

    payload = json.loads(paths.review_artifact.read_text(encoding="utf-8-sig"))
    approved_words = payload.get("approved_candidates", [])

    offline = OfflineJsonDictionary(Path(base_dir) / "dictionaries" / "offline.json")
    online = NullOnlineDictionary()
    enriched = [enrich_word(word, offline=offline, online=online, max_meanings=3) for word in approved_words]

    try:
        import genanki
    except ImportError as exc:
        raise RuntimeError(
            "build command requires 'genanki'. Install with: "
            ".\\.venv\\Scripts\\python -m pip install genanki"
        ) from exc

    deck_name = build_deck_name(source=source, volume=volume, chapter=chapter)
    model_id = _stable_id(f"{source}:{run_id}:model")
    deck_id = _stable_id(f"{source}:{run_id}:deck")

    model = genanki.Model(
        model_id,
        "JP Vocab Basic (Bidirectional)",
        fields=[{"name": "Front"}, {"name": "Back"}],
        templates=[
            {
                "name": "Forward",
                "qfmt": "{{Front}}",
                "afmt": "{{FrontSide}}<hr id=\"answer\">{{Back}}",
            }
        ],
    )
    deck = genanki.Deck(deck_id, deck_name)

    for item in enriched:
        notes = build_bidirectional_fields(
            word=item["word"],
            reading=item.get("reading", ""),
            meanings=item.get("meanings", []),
        )
        for note in notes:
            deck.add_note(genanki.Note(model=model, fields=[note["front"], note["back"]]))

    paths.run_dir.mkdir(parents=True, exist_ok=True)
    package = genanki.Package(deck)
    package.write_to_file(str(paths.deck_package))

    build_payload = {
        "source": source,
        "run_id": run_id,
        "deck_name": deck_name,
        "approved_word_count": len(approved_words),
        "note_count": len(deck.notes),
        "package_path": str(paths.deck_package),
        "enriched": enriched,
    }
    paths.build_artifact.write_text(
        json.dumps(build_payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    return BuildSummary(
        run_id=run_id,
        source=source,
        note_count=len(deck.notes),
        package_path=str(paths.deck_package),
        artifact_path=str(paths.build_artifact),
    )
