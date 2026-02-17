# custom_japanese_anki_decks

CLI tool that turns Japanese text from screenshots into Anki decks.

Recommended OCR backend: `manga-ocr` (best results for manga/game UI text).

## Quick Start (Windows, run-only workflow)

### 1) Set up Python environment

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -U pip
.\.venv\Scripts\python -m pip install -e .
```

### 2) Install recommended OCR + tokenizer extras

```powershell
.\.venv\Scripts\python -m pip install -e ".[manga_ocr,japanese_nlp]"
```

### 3) Install offline dictionary (for local meanings)

```powershell
.\.venv\Scripts\python -m jp_anki_builder.cli install-dictionary `
  --data-dir data `
  --provider jmdict
```

This creates:
- `data/dictionaries/offline.json`

### 4) Run end-to-end in one command

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

Output deck:
- `data/Miharu/Vol01-Ch00/deck.apkg`

Deck name in Anki:
- `Miharu::Vol01::Ch00`

## What `run` does

`run` executes:
1. `scan` (OCR + candidate extraction)
2. `review` (filters known words, particles, already-seen words)
3. `build` (dictionary enrichment + Anki package export)

It stops early with clear messages if:
- scan finds no candidates
- review leaves no approved words
- build has no words with meanings

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
- `data/dictionaries/offline.json` (default), and
- `jisho` (only when `--online-dict jisho` is enabled)

## Folder structure

- Source data: `data/<source>/`
- Per-run artifacts: `data/<source>/<run_id>/`
  - `scan.json`
  - `review.json`
  - `build.json`
  - `deck.apkg`
- Known words (per source): `data/<source>/known_words.txt`
- Seen words (per source): `data/<source>/seen_words.json`

## Common commands

Show help:

```powershell
.\.venv\Scripts\python -m jp_anki_builder.cli --help
```

Run with online fallback enabled:

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

## manga-ocr notes

- First run may be slower while model files initialize.
- Startup logs are reduced by default.
- To show full raw manga-ocr startup logs for debugging:

```powershell
$env:JP_ANKI_MANGA_OCR_DEBUG = "1"
.\.venv\Scripts\python -m jp_anki_builder.cli scan --ocr-mode manga-ocr ...
```

## If something fails

`ModuleNotFoundError: No module named 'jp_anki_builder'`

```powershell
.\.venv\Scripts\python -m pip install -e .
```

Offline meanings missing with `--online-dict off`

```powershell
.\.venv\Scripts\python -m jp_anki_builder.cli install-dictionary --data-dir data --provider jmdict
```

Run tests:

```powershell
.\.venv\Scripts\python -m pytest -q
```

Detailed guide: `docs/usage.md`
