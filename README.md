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

4. If `jpn` is missing, install it:

```powershell
$url = "https://github.com/tesseract-ocr/tessdata_best/raw/main/jpn.traineddata"
$dest = "C:\Program Files\Tesseract-OCR\tessdata\jpn.traineddata"
Invoke-WebRequest -Uri $url -OutFile $dest
& "C:\Program Files\Tesseract-OCR\tesseract.exe" --list-langs
```

## Workflow

The app is organized in stages:

1. `scan` -> OCR + candidate extraction, writes `scan.json`
2. `review` -> filtering and dedup, writes `review.json`
3. `build` -> enrichment + `.apkg` export, writes `build.json`

Run these separately or use one-command `run`.

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
- `data/runs/<run_id>/deck.apkg`
- `data/runs/<run_id>/build.json`

### 4) `run` (all stages)

```powershell
.\.venv\Scripts\python -m jp_anki_builder.cli run `
  --images C:\path\to\screenshots `
  --source my-manga `
  --run-id ch01 `
  --data-dir data `
  --ocr-mode tesseract `
  --online-dict jisho `
  --volume 01 `
  --chapter 01
```

## Data Files

- Known words list: `data/known_words.txt`
- Source dedup index: `data/sources/<source_id>/seen_words.json`
- Run artifacts: `data/runs/<run_id>/`

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
