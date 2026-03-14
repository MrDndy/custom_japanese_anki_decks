# custom_japanese_anki_decks

CLI tool that turns Japanese text from screenshots into Anki decks.

Recommended OCR backend: `manga-ocr` (best results for manga/game UI text).
Recommended Python for NLP normalization: `3.12` (Sudachi wheels are stable on Windows).

## Quick Start (Windows)

### 1) Install

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python -m pip install -U pip
.\.venv\Scripts\python -m pip install -e ".[recommended]"
```

The `recommended` extra installs manga-ocr and Sudachi NLP in one step.

### 2) Install offline dictionary

```powershell
jp-anki-build install-dictionary
```

This creates `data/dictionaries/offline.json`.

Optional: migrate to SQLite for faster lookups and lower memory:

```powershell
jp-anki-build migrate-dictionary
```

### 3) Set your defaults (optional)

```powershell
jp-anki-build config set ocr_mode manga-ocr
jp-anki-build config set online_dict off
```

This saves to `data/.jp-anki.json` so you don't need to pass these flags every time.

You can also set per-source overrides:

```powershell
jp-anki-build config set ocr_mode sidecar --source Miharu
```

View current config:

```powershell
jp-anki-build config show
```

### 4) Run

```powershell
jp-anki-build run --images ./screenshots/Miharu/Prologue
```

That's it. `--source` and `--run-id` are auto-derived from the image path (`source=Miharu`, `run_id=Prologue`). Override them explicitly if needed:

```powershell
jp-anki-build run --images ./screenshots --source Miharu --run-id Prologue
```

Output deck: `data/Miharu/Prologue/deck.apkg`

### Install JLPT level data (optional)

If you have a JLPT word list as JSON (`{"word": level, ...}` where level is 1-5):

```powershell
jp-anki-build install-jlpt --source-file "path\to\jlpt_words.json"
```

Cards will display a JLPT level badge (e.g. N2) when data is available.

## What `run` does

`run` executes:
1. `scan` (OCR + surface token extraction + normalization)
2. `review` (filters known words, particles, already-seen words)
3. `build` (dictionary enrichment + JLPT tagging + Anki package export)

It stops early with clear messages if:
- scan finds no candidates
- review leaves no approved words
- build has no words with meanings

### Dry-run mode

Preview what would happen without writing review/build artifacts or generating a deck:

```powershell
jp-anki-build run --images ./screenshots/Miharu/Prologue --dry-run
```

### Resuming interrupted scans

Scan progress is saved incrementally after each image. Resume with:

```powershell
jp-anki-build run --images ./screenshots/Miharu/Prologue --resume
```

### Path inference

When `--source` and `--run-id` are omitted, they are inferred from the `--images` path:

| `--images` path | Inferred `--source` | Inferred `--run-id` |
|---|---|---|
| `./screenshots/Miharu/Prologue` | `Miharu` | `Prologue` |
| `C:\imgs\GameX\Ch01` | `GameX` | `Ch01` |

You can always override either one explicitly.

### What "approved words" means

Approved words are the candidates that survive review and are allowed to move to build.

A word is usually excluded before build if it is:
- in `data/<source>/known_words.txt`
- a filtered particle/stop token
- already present in `data/<source>/seen_words.json`
- manually excluded with `--exclude`

Known words idea:
- `known_words.txt` is your per-source "already know this" list.
- Put words here to reduce review noise and avoid generating cards for vocabulary you do not want to study.
- You can also add words during review with `--save-excluded-to-known`.

Even approved words can still be skipped in build if no meaning is found in:
- `data/dictionaries/offline.json` or `offline.db` (default), and
- `jisho` (only when `--online-dict jisho` is enabled)

## Configuration

Config files store defaults so CLI commands can be shorter.

| Level | File | Purpose |
|---|---|---|
| Project | `data/.jp-anki.json` | Defaults for all sources |
| Source | `data/<source>/.jp-anki.json` | Overrides for a specific source |

Source-level overrides project-level. CLI flags always win over both.

Manage config via CLI:

```powershell
jp-anki-build config show                          # show project config
jp-anki-build config show --source Miharu           # show source config
jp-anki-build config set ocr_mode manga-ocr         # set project default
jp-anki-build config set ocr_mode sidecar --source Miharu  # set source override
jp-anki-build config unset volume                   # remove a key
```

Valid keys: `ocr_mode`, `ocr_language`, `tesseract_cmd`, `online_dict`, `data_dir`, `no_preprocess`, `volume`, `chapter`.

## Folder structure

- Project config: `data/.jp-anki.json`
- Source config: `data/<source>/.jp-anki.json`
- Source data: `data/<source>/`
- Per-run artifacts: `data/<source>/<run_id>/`
  - `scan.json`, `review.json`, `build.json`, `deck.apkg`
  - `word_cache.json` (shared dictionary lookup cache)
- Known words (per source): `data/<source>/known_words.txt`
- Seen words (per source): `data/<source>/seen_words.json`
- Offline dictionary: `data/dictionaries/offline.json` or `offline.db`
- JLPT levels (optional): `data/dictionaries/jlpt_levels.json`

## Common commands

```powershell
jp-anki-build --help                                # show all commands
jp-anki-build run --images ./path/to/screenshots     # full pipeline
jp-anki-build run --images ./path --dry-run          # preview only
jp-anki-build run --images ./path --resume           # resume interrupted scan
jp-anki-build run --images ./path --online-dict jisho  # with online fallback
jp-anki-build config show                            # view config
jp-anki-build install-dictionary                     # install JMdict
jp-anki-build migrate-dictionary                     # convert to SQLite
```

## manga-ocr notes

- First run may be slower while model files initialize.
- Startup logs are reduced by default.
- To show full raw manga-ocr startup logs for debugging:

```powershell
$env:JP_ANKI_MANGA_OCR_DEBUG = "1"
jp-anki-build scan --images ./path --ocr-mode manga-ocr
```

## If something fails

`ModuleNotFoundError: No module named 'jp_anki_builder'`

```powershell
.\.venv\Scripts\python -m pip install -e .
```

Offline meanings missing with `--online-dict off`

```powershell
jp-anki-build install-dictionary
```

Run tests:

```powershell
.\.venv\Scripts\python -m pytest -q
```

Detailed guide: `docs/usage.md`
