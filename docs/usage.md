# Usage Guide

This guide is optimized for the simplest workflow: use `run` and let the app handle scan, review, and build.

## Recommended Setup

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -U pip
.\.venv\Scripts\python -m pip install -e ".[recommended]"
jp-anki-build install-dictionary
```

Why this setup:
- `recommended` installs manga-ocr + Sudachi NLP in one step.
- `install-dictionary` downloads JMdict for local meanings.

### Optional: SQLite dictionary

For large dictionaries, migrate to SQLite for faster lookups and lower memory:

```powershell
jp-anki-build migrate-dictionary
```

Creates `data/dictionaries/offline.db`. When both exist, SQLite is used automatically.

### Optional: JLPT level data

Install a JLPT word list to tag cards with difficulty levels (N1-N5):

```powershell
jp-anki-build install-jlpt --source-file "path\to\jlpt_words.json"
```

Expected format: `{"食べる": 5, "冒険": 2, ...}` (word to JLPT level 1-5).

## Quickstart

### Set your defaults once

```powershell
jp-anki-build config set ocr_mode manga-ocr
```

### Run

```powershell
jp-anki-build run --images ./screenshots/Miharu/Prologue
```

`--source` and `--run-id` are auto-derived from the path. Output: `data/Miharu/Prologue/deck.apkg`.

Override explicitly when needed:

```powershell
jp-anki-build run --images ./screenshots --source Miharu --run-id Prologue --volume 01 --chapter 00
```

## Configuration

Config files store defaults so you don't repeat flags.

| Level | File | Purpose |
|---|---|---|
| Project | `data/.jp-anki.json` | Defaults for all sources |
| Source | `data/<source>/.jp-anki.json` | Overrides for a specific source |

Manage via CLI:

```powershell
jp-anki-build config show                              # view project config
jp-anki-build config show --source Miharu               # view source config
jp-anki-build config set ocr_mode manga-ocr             # set project default
jp-anki-build config set ocr_mode sidecar --source Miharu  # source override
jp-anki-build config unset volume                       # remove a key
```

Valid keys: `ocr_mode`, `ocr_language`, `tesseract_cmd`, `online_dict`, `data_dir`, `no_preprocess`, `volume`, `chapter`.

Precedence: CLI flags > source config > project config > built-in defaults.

## What Run Does

`run` executes:
1. `scan` (OCR + candidate extraction + normalization)
2. `review` (filters known/particle/already-seen words)
3. `build` (dictionary enrichment + JLPT tagging + deck export)

Early exit behavior:
- no scan candidates -> stop
- no review-approved words -> stop
- no buildable meanings -> stop with remediation

### Dry-run mode

Preview candidates and filtering without writing review/build artifacts or a deck:

```powershell
jp-anki-build run --images ./screenshots/Miharu/Prologue --dry-run
```

### Resuming interrupted scans

Scan progress is saved incrementally after each image. Resume with `--resume`:

```powershell
jp-anki-build run --images ./screenshots/Miharu/Prologue --resume
```

### Path inference

When `--source` and `--run-id` are omitted, they're inferred from `--images`:

| `--images` path | `--source` | `--run-id` |
|---|---|---|
| `./screenshots/Miharu/Prologue` | `Miharu` | `Prologue` |
| `C:\imgs\GameX\Ch01` | `GameX` | `Ch01` |

## OCR Notes

OCR modes:
- `manga-ocr` (default, recommended)
- `tesseract`
- `sidecar` (dev/testing with `.txt` files)

`manga-ocr` notes:
- first run may be slower while model initializes
- startup logs are reduced by default
- enable raw startup logs:

```powershell
$env:JP_ANKI_MANGA_OCR_DEBUG = "1"
jp-anki-build scan --images ./path --ocr-mode manga-ocr
```

Compound behavior in scan:
- adjacent token compounds are detected
- when a merged compound exists, both are kept
- merge checks use offline dictionary first, optional `jisho` fallback when enabled

## Data Layout

- Project config: `data/.jp-anki.json`
- Source config: `data/<source>/.jp-anki.json`
- per-source root: `data/<source>/`
- per-run folder: `data/<source>/<run_id>/`
  - `scan.json`, `review.json`, `build.json`, `deck.apkg`
  - `word_cache.json` (shared dictionary lookup cache between stages)
- per-source known words: `data/<source>/known_words.txt`
- per-source seen words: `data/<source>/seen_words.json`
- offline dictionary: `data/dictionaries/offline.json` or `offline.db`
- JLPT levels (optional): `data/dictionaries/jlpt_levels.json`

## Useful Commands

```powershell
jp-anki-build --help                                   # show all commands
jp-anki-build run --images ./path                       # full pipeline
jp-anki-build run --images ./path --dry-run             # preview only
jp-anki-build run --images ./path --resume              # resume interrupted
jp-anki-build run --images ./path --online-dict jisho   # online fallback
jp-anki-build config show                               # view config
jp-anki-build config set ocr_mode manga-ocr             # set default
jp-anki-build install-dictionary                        # install JMdict
jp-anki-build migrate-dictionary                        # convert to SQLite
```

## Troubleshooting

`ModuleNotFoundError: No module named 'jp_anki_builder'`

```powershell
.\.venv\Scripts\python -m pip install -e .
```

No meanings when using `--online-dict off`

```powershell
jp-anki-build install-dictionary
```

## Verification

```powershell
.\.venv\Scripts\python -m pytest -q
```
