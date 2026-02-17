# Usage Guide

## Current Commands

- `scan`: reads screenshots, runs OCR, extracts candidate tokens, writes `scan.json`.
- `review`: filters candidates (particles, known words, source dedup), writes `review.json`.
- `build`: enriches approved words and exports Anki deck package (`deck.apkg`).
- `run`: executes `scan -> review -> build` in one command.

## OCR Modes

- `tesseract` (default): real OCR from screenshots.
- `manga-ocr`: model tuned for manga-style Japanese OCR (recommended for manga/game UI text).
- `sidecar`: reads text from `*.txt` files next to images (testing/dev mode).

Notes for `manga-ocr`:

- Startup logs from third-party libraries are reduced by default.
- First load may still be slower due to model initialization and local cache checks.
- Set `JP_ANKI_MANGA_OCR_DEBUG=1` to re-enable raw startup logs when troubleshooting.

Compound merge note:

- During `scan`, adjacent tokens are checked for merged compounds.
- If a merged form exists in dictionary data, scan keeps both:
  - original split tokens
  - merged compound token
- Validation is offline dictionary first, with optional online fallback when `--online-dict jisho` is enabled.

## Tokenization

- Preferred path: install `fugashi` + `unidic-lite` (`.[japanese_nlp]`) for word-level extraction.
- Fallback path: regex chunk extraction when tokenizer deps are unavailable.

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

`run` is stage-gated. It exits early with actionable feedback when:
- scan finds zero candidates
- review leaves zero approved words
- build finds zero words with meanings

## Review Behavior

`review` applies these filters in order:

1. Known words from `data/<source>/known_words.txt`
2. Built-in particles/function words
3. Words already seen in `data/<source>/seen_words.json`
4. Manual excludes (`--exclude ...`)

If `--save-excluded-to-known` is set, manual excludes are appended to `data/<source>/known_words.txt`.

CLI output now includes skipped-word reporting by reason:

- known words
- particles
- already-seen words
- manually excluded words

Interactive mode:

- Use `review --interactive` to see filtered candidates and exclude by index.
- You can confirm saving excluded words to known words during the prompt flow.

## Artifacts

Run output directory:

- `data/<source>/<run_id>/scan.json`
- `data/<source>/<run_id>/review.json`
- `data/<source>/<run_id>/build.json`
- `data/<source>/<run_id>/deck.apkg`

## Offline Dictionary

Current build step reads:

- `data/dictionaries/offline.json`

To install a local dictionary file:

```powershell
.\.venv\Scripts\python -m jp_anki_builder.cli install-dictionary `
  --data-dir data `
  --provider jmdict
```

Optional online fallback:

- `--online-dict off` (default)
- `--online-dict jisho` (queries Jisho API for missing words)

Example shape:

```json
{
  "word": {
    "reading": "reading",
    "meanings": ["meaning1", "meaning2"]
  }
}
```

## Build Behavior (Meaning Gate)

- `build` only creates cards for words that have at least one English meaning.
- Words with missing meanings are skipped and printed in CLI output.
- `build.json` records:
  - `approved_word_count`
  - `buildable_word_count`
  - `missing_meaning_count`
  - `missing_meaning_words`
- If zero buildable words remain, the command fails with a remediation message:
  - `No cards were created for this run.`
  - `Missing meaning (N): ...`
  - `Use --online-dict jisho or populate data/dictionaries/offline.json`

## Verification

```powershell
.\.venv\Scripts\python -m pytest -q
.\.venv\Scripts\python -m jp_anki_builder.cli --help
```

## Enhancement Notes

- Planned for a later version: optional long-lived OCR session mode for faster repeated manga-ocr runs (especially useful for a future GUI).
