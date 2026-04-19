# JP Anki Builder — Windows Packaging

## Prerequisites

- Python 3.12+
- All project dependencies installed (see `pyproject.toml`)
- PyInstaller: `pip install pyinstaller`

## Building

From the project root:

```bash
python packaging/build.py
```

This produces `dist/jp-anki-build/` — a self-contained directory distribution.

## Testing the build

```bash
# Show help
dist\jp-anki-build\jp-anki-build.exe --help

# Launch GUI
dist\jp-anki-build\jp-anki-build.exe gui

# Launch real-time overlay
dist\jp-anki-build\jp-anki-build.exe overlay

# Run batch pipeline
dist\jp-anki-build\jp-anki-build.exe run --images path\to\manga\pages
```

## What's included

- Python runtime and all core dependencies
- manga-ocr (Japanese OCR model — downloads on first use)
- fugashi + unidic-lite (MeCab tokenizer + dictionary)
- SudachiPy + sudachidict_core (morphological analyzer)
- PySide6 (Qt GUI framework)
- genanki (Anki deck generation)
- pynput (global hotkeys for real-time overlay)
- pysubs2 (subtitle parsing)

## What's NOT included (optional, install separately)

### PaddleOCR (region detection for full manga pages)

PaddleOCR + PaddlePaddle are too large to bundle (~1 GB). If you need
full-page manga region detection, install them in the system Python:

```bash
pip install paddlepaddle==2.6.2 paddleocr==2.10.0 "albumentations<2"
```

Then set the detector mode to `paddleocr` in the GUI settings or CLI.

Without PaddleOCR, the batch pipeline still works — it processes entire
images as single regions (suitable for pre-cropped speech bubble screenshots).

### FFmpeg (subtitle extraction from video)

Subtitle extraction requires `ffprobe` on PATH. Install FFmpeg from
https://ffmpeg.org/download.html or via `winget install ffmpeg`.

## Creating a Windows installer

To create a distributable `.exe` installer, use [Inno Setup](https://jrsoftware.org/isinfo.php):

1. Install Inno Setup
2. Create a new script pointing to `dist/jp-anki-build/` as the source
3. Set the main executable to `jp-anki-build.exe`
4. Configure the installer name, icon, and start menu entries
5. Compile to produce a single installer `.exe`

Example Inno Setup script sections:

```ini
[Setup]
AppName=JP Anki Builder
AppVersion=0.1.0
DefaultDirName={autopf}\JP Anki Builder
OutputBaseFilename=jp-anki-builder-setup
SetupIconFile=packaging\icon.ico

[Files]
Source: "dist\jp-anki-build\*"; DestDir: "{app}"; Flags: recursesubdirs

[Icons]
Name: "{group}\JP Anki Builder"; Filename: "{app}\jp-anki-build.exe"; Parameters: "gui"
```

## Troubleshooting

- **Missing DLLs**: If the packaged app fails to start, ensure Visual C++
  Redistributable 2015-2022 is installed on the target machine.
- **manga-ocr model**: The OCR model downloads automatically on first use
  (~400 MB). Ensure internet access for the first run, or pre-populate
  the huggingface cache.
- **Large bundle size**: The distribution is large (~1-2 GB) due to PyTorch,
  manga-ocr, and dictionary data. This is expected for a directory distribution.
