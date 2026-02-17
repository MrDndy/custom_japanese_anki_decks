from __future__ import annotations

import json
import random
from dataclasses import dataclass
from pathlib import Path

from jp_anki_builder.cards import build_deck_name, build_note_fields
from jp_anki_builder.config import RunPaths
from jp_anki_builder.dictionary import JishoOnlineDictionary, NullOnlineDictionary, OfflineJsonDictionary
from jp_anki_builder.enrich import enrich_word


@dataclass
class BuildSummary:
    run_id: str
    source: str
    note_count: int
    package_path: str
    artifact_path: str
    approved_word_count: int
    buildable_word_count: int
    missing_meaning_words: list[str]
    buildable_words: list[str]


class NoBuildableWordsError(RuntimeError):
    def __init__(self, approved_words: list[str], missing_meaning_words: list[str]):
        super().__init__("no buildable words")
        self.approved_words = approved_words
        self.missing_meaning_words = missing_meaning_words


def _stable_id(seed_text: str) -> int:
    random.seed(seed_text)
    return random.randint(1_000_000_000, 2_000_000_000)


def _model_id() -> int:
    # Keep model id stable so repeated imports reuse one note type.
    return _stable_id("jp-anki-builder:jp-vocab-basic-bidirectional:v1")


def _deck_id(deck_name: str) -> int:
    # Keep deck id stable per hierarchy name across runs.
    return _stable_id(f"deck:{deck_name}")


def run_build(
    source: str,
    run_id: str,
    base_dir: str = "data",
    volume: str | None = None,
    chapter: str | None = None,
    online_dict: str = "off",
) -> BuildSummary:
    paths = RunPaths(base_dir=base_dir, source_id=source, run_id=run_id)
    if not paths.review_artifact.exists():
        raise ValueError(f"review artifact not found: {paths.review_artifact}")

    payload = json.loads(paths.review_artifact.read_text(encoding="utf-8-sig"))
    approved_words = payload.get("approved_candidates", [])

    offline = OfflineJsonDictionary(Path(base_dir) / "dictionaries" / "offline.json")
    if online_dict == "off":
        online = NullOnlineDictionary()
    elif online_dict == "jisho":
        online = JishoOnlineDictionary()
    else:
        raise ValueError("unsupported online dictionary mode. Use: off or jisho.")

    enriched = [enrich_word(word, offline=offline, online=online, max_meanings=3) for word in approved_words]
    buildable = [item for item in enriched if item.get("meanings")]
    missing_meaning_words = [item["word"] for item in enriched if not item.get("meanings")]

    if not buildable:
        raise NoBuildableWordsError(
            approved_words=approved_words,
            missing_meaning_words=missing_meaning_words,
        )

    try:
        import genanki
    except ImportError as exc:
        raise RuntimeError(
            "build command requires 'genanki'. Install with: "
            ".\\.venv\\Scripts\\python -m pip install genanki"
        ) from exc

    deck_name = build_deck_name(source=source, volume=volume, chapter=chapter)
    model_id = _model_id()
    deck_id = _deck_id(deck_name)

    model = genanki.Model(
        model_id,
        "JP Vocab Basic (Bidirectional)",
        fields=[{"name": "Kanji"}, {"name": "Reading"}, {"name": "Meaning"}],
        templates=[
            {
                "name": "Forward",
                "qfmt": (
                    "{{#Reading}}<div class=\"jp-reading japanese\" lang=\"ja\">{{Reading}}</div>{{/Reading}}"
                    "<div class=\"jp-kanji japanese\" lang=\"ja\">{{Kanji}}</div>"
                ),
                "afmt": (
                    "{{FrontSide}}<hr id=\"answer\">"
                    "<div class=\"label\">Meaning:</div>"
                    "<div class=\"text en-meaning\">{{Meaning}}</div>"
                ),
            },
            {
                "name": "Reverse",
                "qfmt": (
                    "<div class=\"label\">Meaning:</div>"
                    "<div class=\"text en-meaning\">{{Meaning}}</div>"
                ),
                "afmt": (
                    "{{FrontSide}}<hr id=\"answer\">"
                    "{{#Reading}}<div class=\"jp-reading japanese\" lang=\"ja\">{{Reading}}</div>{{/Reading}}"
                    "<div class=\"jp-kanji japanese\" lang=\"ja\">{{Kanji}}</div>"
                ),
            },
        ],
        css="""
.card {
  font-family: "Noto Sans Japanese";
  font-size: 20px;
  text-align: center;
}

@font-face {
  font-family: "Noto Sans Japanese";
  src: url("_NotoSansCJKjp-Regular.woff2") format("woff2");
}

.japanese {
  font-family: "Noto Sans Japanese";
}

.jp-kanji {
  font-size: 42px;
  line-height: 1.2;
}

.jp-reading {
  font-size: 28px;
  color: #c0c0c0;
  line-height: 1.2;
  margin-bottom: 4px;
}

.label {
  font-size: 14px;
  color: #c0c0c0;
  margin-top: 8px;
}

.text {
  font-family: "Noto Sans Japanese";
}

.en-meaning {
  font-size: 30px;
  margin-top: 6px;
}
""",
    )
    deck = genanki.Deck(deck_id, deck_name)

    for item in buildable:
        note = build_note_fields(
            word=item["word"],
            reading=item.get("reading", ""),
            meanings=item.get("meanings", []),
        )
        deck.add_note(
            genanki.Note(
                model=model,
                fields=[note["kanji"], note["reading"], note["meaning"]],
                # Stable per deck+word so re-imports update instead of duplicating.
                guid=genanki.guid_for(deck_name, note["kanji"]),
            )
        )

    paths.run_dir.mkdir(parents=True, exist_ok=True)
    package = genanki.Package(deck)
    package.write_to_file(str(paths.deck_package))

    build_payload = {
        "source": source,
        "run_id": run_id,
        "deck_name": deck_name,
        "approved_word_count": len(approved_words),
        "buildable_word_count": len(buildable),
        "missing_meaning_count": len(missing_meaning_words),
        "missing_meaning_words": missing_meaning_words,
        "note_count": len(buildable) * 2,
        "package_path": str(paths.deck_package),
        "online_dict": online_dict,
        "enriched": enriched,
    }
    paths.build_artifact.write_text(
        json.dumps(build_payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    return BuildSummary(
        run_id=run_id,
        source=source,
        note_count=len(buildable) * 2,
        package_path=str(paths.deck_package),
        artifact_path=str(paths.build_artifact),
        approved_word_count=len(approved_words),
        buildable_word_count=len(buildable),
        missing_meaning_words=missing_meaning_words,
        buildable_words=[item["word"] for item in buildable],
    )
