# custom_japanese_anki_decks

CLI tool to turn Japanese screenshot text into Anki decks.

## Quick Start (Windows PowerShell)

1. Create and prepare virtual environment:

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -U pip
.\.venv\Scripts\python -m pip install -e .
```

Optional (recommended) Japanese tokenizer quality upgrade:

```powershell
.\.venv\Scripts\python -m pip install -e ".[japanese_nlp]"
```

Optional manga-specific OCR backend (best for manga/game UI text):

```powershell
.\.venv\Scripts\python -m pip install -e ".[manga_ocr]"
```

2. Confirm CLI works:

```powershell
.\.venv\Scripts\python -m jp_anki_builder.cli --help
```

## Install Tesseract OCR

`scan` and `run` default to `--ocr-mode tesseract`, so install Tesseract first.

### Option A: winget

```powershell
winget install --id UB-Mannheim.TesseractOCR -e
```

### Option B: manual install

- Install Tesseract from the UB Mannheim Windows build.
- Add the Tesseract install folder to your `PATH`.

If needed, you can pass the executable path directly:

```powershell
--tesseract-cmd "C:\Program Files\Tesseract-OCR\tesseract.exe"
```

### Required post-install checks (Windows)

1. Verify executable:

```powershell
& "C:\Program Files\Tesseract-OCR\tesseract.exe" --version
```

2. Add Tesseract to your **User PATH** (if `tesseract` is not recognized):

```powershell
$tDir = "C:\Program Files\Tesseract-OCR"
$userPath = [Environment]::GetEnvironmentVariable("Path","User")
if ($userPath -notlike "*$tDir*") {
  [Environment]::SetEnvironmentVariable("Path", "$userPath;$tDir", "User")
}
```

Then close and reopen your terminal.

3. Verify language data:

```powershell
& "C:\Program Files\Tesseract-OCR\tesseract.exe" --list-langs
```

You should see `jpn` in the list.

Recommended: also install `jpn_vert` for better handling of vertical Japanese text.

4. If `jpn` is missing, install it:

```powershell
$url = "https://github.com/tesseract-ocr/tessdata_best/raw/main/jpn.traineddata"
$dest = "C:\Program Files\Tesseract-OCR\tessdata\jpn.traineddata"
Invoke-WebRequest -Uri $url -OutFile $dest
& "C:\Program Files\Tesseract-OCR\tesseract.exe" --list-langs
```

If `jpn_vert` is missing, install it the same way:

```powershell
$url = "https://github.com/tesseract-ocr/tessdata_best/raw/main/jpn_vert.traineddata"
$dest = "C:\Program Files\Tesseract-OCR\tessdata\jpn_vert.traineddata"
Invoke-WebRequest -Uri $url -OutFile $dest
& "C:\Program Files\Tesseract-OCR\tesseract.exe" --list-langs
```

## Workflow

The app is organized in stages:

1. `scan` -> OCR + candidate extraction, writes `scan.json`
2. `review` -> filtering and dedup, writes `review.json`
3. `build` -> enrichment + `.apkg` export, writes `build.json`

Run these separately or use one-command `run`.

`run` now has stage gates:
- stops after `scan` if zero candidates are detected
- stops after `review` if zero approved words remain
- only reaches `build` when there is something actionable

## Install Offline Dictionary (Recommended)

If `--online-dict off` returns no meanings, your offline dictionary is likely missing.

Install JMdict locally:

```powershell
.\.venv\Scripts\python -m jp_anki_builder.cli install-dictionary `
  --data-dir data `
  --provider jmdict
```

This writes:
- `data/dictionaries/offline.json`

## Command Guide

### 1) `scan`

```powershell
.\.venv\Scripts\python -m jp_anki_builder.cli scan `
  --images C:\path\to\screenshots `
  --source my-manga `
  --run-id ch01 `
  --data-dir data `
  --ocr-mode tesseract `
  --ocr-language jpn
```

Useful options:
- `--tesseract-cmd <path>`: set explicit tesseract executable path
- `--no-preprocess`: disable image preprocessing
- `--ocr-mode sidecar`: dev mode; reads `image.txt` next to `image.png`
- `--ocr-mode manga-ocr`: alternative OCR engine tuned for manga-style Japanese text
- `--online-dict jisho`: optional online fallback for compound candidate detection during scan

### 2) `review`

```powershell
.\.venv\Scripts\python -m jp_anki_builder.cli review `
  --source my-manga `
  --run-id ch01 `
  --data-dir data `
  --interactive `
  --exclude already_known_word `
  --save-excluded-to-known
```

What it does:
- removes particles and known words
- removes words already seen in same source
- stores approved words for build stage
- prints skipped words by reason in CLI output:
  - known words
  - particles
  - already-seen words
  - manually excluded words

Candidate behavior note:
- scan now tries adjacent-token compound merges (keeps both split tokens and merged token when the merged form exists in dictionary data).

### 3) `build`

```powershell
.\.venv\Scripts\python -m jp_anki_builder.cli build `
  --source my-manga `
  --run-id ch01 `
  --data-dir data `
  --online-dict jisho `
  --volume 01 `
  --chapter 01
```

Output:
- `data/<source>/<run_id>/deck.apkg`
- `data/<source>/<run_id>/build.json`
- CLI prints any skipped words that had no meanings.

Important build rule:
- words with no English meanings are skipped (no blank-back cards)
- if all approved words are missing meanings, `build` exits with a friendly summary:
  - `No cards were created for this run.`
  - `Missing meaning (N): ...`
  - next steps to use `--online-dict jisho` or add entries to `data/dictionaries/offline.json`

### 4) `run` (all stages)

```powershell
.\.venv\Scripts\python -m jp_anki_builder.cli run `
  --images C:\path\to\screenshots `
  --source my-manga `
  --run-id ch01 `
  --data-dir data `
  --ocr-mode manga-ocr `
  --online-dict jisho `
  --volume 01 `
  --chapter 01
```

## Data Files

- Known words list: `data/<source>/known_words.txt`
- Source dedup index: `data/<source>/seen_words.json`
- Run artifacts: `data/<source>/<run_id>/`

## Troubleshooting

### `ModuleNotFoundError: No module named 'jp_anki_builder'`

Run:

```powershell
.\.venv\Scripts\python -m pip install -e .
```

Then use:

```powershell
.\.venv\Scripts\python -m jp_anki_builder.cli --help
```

### `Tesseract executable not found`

- Install Tesseract.
- Ensure it is on `PATH`, or pass `--tesseract-cmd`.

Quick fix command:

```powershell
.\.venv\Scripts\python -m jp_anki_builder.cli scan `
  --images C:\path\to\screenshots `
  --source test `
  --run-id test `
  --ocr-mode tesseract `
  --tesseract-cmd "C:\Program Files\Tesseract-OCR\tesseract.exe"
```

### `Error opening data file ... jpn.traineddata`

Install Japanese language data (`jpn.traineddata`) into:

- `C:\Program Files\Tesseract-OCR\tessdata\`

### OCR not reading text well

- Try higher-resolution screenshots.
- Keep text horizontal.
- Toggle preprocessing with/without `--no-preprocess`.

### manga-ocr startup is noisy or slow

- The CLI now configures manga-ocr/transformers/huggingface logging to reduce non-actionable startup output.
- First run is usually slower because model files are loaded (or downloaded once if missing). Later runs reuse local cache.
- To see full raw third-party startup logs for debugging:

```powershell
$env:JP_ANKI_MANGA_OCR_DEBUG = "1"
.\.venv\Scripts\python -m jp_anki_builder.cli scan --ocr-mode manga-ocr ...
```

### Candidate extraction quality is low

Install tokenizer extras:

```powershell
.\.venv\Scripts\python -m pip install -e ".[japanese_nlp]"
```

Without these extras, the app falls back to regex chunk extraction.

## Development

Run tests:

```powershell
.\.venv\Scripts\python -m pytest -q
```

For more details: `docs/usage.md`
