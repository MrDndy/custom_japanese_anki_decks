# Usage Guide

## Commands

- `scan` prepares OCR output and token candidates from screenshot inputs.
- `review` removes particles, known words, and source-seen duplicates, then supports interactive approval.
- `build` enriches approved words (offline first, online fallback) and maps two card directions.
- `run` executes `scan -> review -> build`.

## Known Words

Use `data/known_words.txt` to store words that should be auto-excluded on future runs.

Optional review behavior can append removals to this file (`save-to-known-list`).

## Source-Level Dedup

Each source keeps a seen-word index at:

- `data/sources/<source_id>/seen_words.json`

Words approved in one chapter are skipped in later chapters for the same source.

## Deck Naming

Deck naming follows:

- `Source::VolumeXX::ChapterYY`

If volume or chapter is missing, omitted levels are not included.

## Artifacts

Run artifacts are intended to live under:

- `data/runs/<run_id>/`

These artifacts support resume/review without repeating OCR.

## Testing

Run all tests:

```bash
.\.venv\Scripts\python -m pytest -q
```

Run CLI help:

```bash
.\.venv\Scripts\python -m jp_anki_builder.cli --help
```
