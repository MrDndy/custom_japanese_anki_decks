# custom_japanese_anki_decks

Python CLI MVP for turning Japanese screenshot text into organized Anki decks.

## Setup

```bash
python -m venv .venv
.\.venv\Scripts\python -m pip install -U pip
.\.venv\Scripts\python -m pip install -e . pytest typer
```

## CLI Commands

```bash
.\.venv\Scripts\python -m jp_anki_builder.cli --help
.\.venv\Scripts\python -m jp_anki_builder.cli scan
.\.venv\Scripts\python -m jp_anki_builder.cli review
.\.venv\Scripts\python -m jp_anki_builder.cli build
.\.venv\Scripts\python -m jp_anki_builder.cli run
```

## Workflow

- `scan`: reads screenshots and prepares OCR/token artifacts.
- `review`: applies known words + particle filtering and source-level dedup.
- `build`: enriches words and builds bidirectional card fields for export.
- `run`: executes `scan -> review -> build`.

## Organization Model

- Hierarchical deck naming target: `Source::VolumeXX::ChapterYY`.
- Known words list path: `data/known_words.txt`.
- Source dedup index path: `data/sources/<source_id>/seen_words.json`.

See `docs/usage.md` for details.
