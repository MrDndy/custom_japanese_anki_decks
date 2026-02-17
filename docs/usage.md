# Usage Guide

This guide is optimized for the simplest workflow: use `run` and let the app handle scan, review, and build.

## Recommended Setup

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -U pip
.\.venv\Scripts\python -m pip install -e .
.\.venv\Scripts\python -m pip install -e ".[manga_ocr,japanese_nlp]"
.\.venv\Scripts\python -m jp_anki_builder.cli install-dictionary --data-dir data --provider jmdict
```

Why this setup:
- `manga-ocr` gives better OCR quality for manga/game UI text.
- `japanese_nlp` improves tokenization quality.
- `jmdict` enables local meanings with `--online-dict off`.

## Quickstart (Run Command Only)

```powershell
.\.venv\Scripts\python -m jp_anki_builder.cli run `
  --images "C:\path\to\screenshots" `
  --source "Miharu" `
  --run-id "Vol01-Ch00" `
  --data-dir data `
  --ocr-mode manga-ocr `
  --online-dict off `
  --volume 01 `
  --chapter 00
```

Output:
- `data/Miharu/Vol01-Ch00/deck.apkg`
- deck name in Anki: `Miharu::Vol01::Ch00`

## What Run Does

`run` executes:
1. `scan` (OCR + candidate extraction)
2. `review` (filters known/particle/already-seen words)
3. `build` (dictionary enrichment + deck export)

Early exit behavior:
- no scan candidates -> stop
- no review-approved words -> stop
- no buildable meanings -> stop with remediation

## OCR Notes

OCR modes:
- `manga-ocr` (recommended)
- `tesseract`
- `sidecar` (dev/testing with `.txt` files)

`manga-ocr` notes:
- first run may be slower while model initializes
- startup logs are reduced by default
- enable raw startup logs:

```powershell
$env:JP_ANKI_MANGA_OCR_DEBUG = "1"
.\.venv\Scripts\python -m jp_anki_builder.cli scan --ocr-mode manga-ocr ...
```

Compound behavior in scan:
- adjacent token compounds are detected
- when a merged compound exists, both are kept:
  - split tokens
  - merged compound token
- merge checks use offline dictionary first, optional `jisho` fallback when enabled

## Data Layout

- per-source root: `data/<source>/`
- per-run folder: `data/<source>/<run_id>/`
  - `scan.json`
  - `review.json`
  - `build.json`
  - `deck.apkg`
- per-source known words: `data/<source>/known_words.txt`
- per-source seen words: `data/<source>/seen_words.json`
- offline dictionary: `data/dictionaries/offline.json`

## Useful Commands

Show help:

```powershell
.\.venv\Scripts\python -m jp_anki_builder.cli --help
```

Run with online fallback:

```powershell
.\.venv\Scripts\python -m jp_anki_builder.cli run `
  --images "C:\path\to\screenshots" `
  --source "Miharu" `
  --run-id "Vol01-Ch01" `
  --data-dir data `
  --ocr-mode manga-ocr `
  --online-dict jisho `
  --volume 01 `
  --chapter 01
```

Reinstall offline dictionary:

```powershell
.\.venv\Scripts\python -m jp_anki_builder.cli install-dictionary --data-dir data --provider jmdict
```

## Troubleshooting

`ModuleNotFoundError: No module named 'jp_anki_builder'`

```powershell
.\.venv\Scripts\python -m pip install -e .
```

No meanings when using `--online-dict off`

```powershell
.\.venv\Scripts\python -m jp_anki_builder.cli install-dictionary --data-dir data --provider jmdict
```

## Verification

```powershell
.\.venv\Scripts\python -m pytest -q
```

## Enhancement Note

- Future version: optional long-lived session mode for faster repeated OCR runs (especially for a GUI).
