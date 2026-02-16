# Usage Guide

## Current Commands

- `scan`: reads screenshots, runs OCR, extracts candidate tokens, writes `scan.json`.
- `review`: filters candidates (particles, known words, source dedup), writes `review.json`.
- `build`: enriches approved words and exports Anki deck package (`deck.apkg`).
- `run`: executes `scan -> review -> build` in one command.

## OCR Modes

- `tesseract` (default): real OCR from screenshots.
- `sidecar`: reads text from `*.txt` files next to images (testing/dev mode).

## Example End-to-End

```powershell
.\.venv\Scripts\python -m jp_anki_builder.cli run `
  --images C:\path\to\screenshots `
  --source my-source `
  --run-id my-run-001 `
  --data-dir data `
  --ocr-mode tesseract `
  --volume 01 `
  --chapter 01
```

## Review Behavior

`review` applies these filters in order:

1. Known words from `data/known_words.txt`
2. Built-in particles/function words
3. Words already seen in `data/sources/<source_id>/seen_words.json`
4. Manual excludes (`--exclude ...`)

If `--save-excluded-to-known` is set, manual excludes are appended to `known_words.txt`.

## Artifacts

Run output directory:

- `data/runs/<run_id>/scan.json`
- `data/runs/<run_id>/review.json`
- `data/runs/<run_id>/build.json`
- `data/runs/<run_id>/deck.apkg`

## Offline Dictionary

Current build step reads:

- `data/dictionaries/offline.json`

Example shape:

```json
{
  "word": {
    "reading": "reading",
    "meanings": ["meaning1", "meaning2"]
  }
}
```

## Verification

```powershell
.\.venv\Scripts\python -m pytest -q
.\.venv\Scripts\python -m jp_anki_builder.cli --help
```
