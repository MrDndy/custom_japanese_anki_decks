@echo off
REM ============================================================
REM  JP Anki Builder — Real-Time Overlay install script
REM  Run this from the project root directory.
REM ============================================================

echo.
echo === Installing JP Anki Builder with real-time overlay support ===
echo.

REM Core package + all overlay dependencies
echo [1/5] Installing core package + overlay dependencies (PySide6, dxcam, pynput)...
.venv\Scripts\pip.exe install -e ".[realtime]"
if errorlevel 1 goto error

REM Japanese NLP (tokenizer + normalizer — required for OCR output to make sense)
echo.
echo [2/5] Installing Japanese NLP (fugashi, SudachiPy, unidic)...
.venv\Scripts\pip.exe install -e ".[japanese_nlp]"
if errorlevel 1 goto error

REM Manga-OCR model (the default OCR backend for the overlay)
echo.
echo [3/5] Installing manga-ocr...
.venv\Scripts\pip.exe install -e ".[manga_ocr]"
if errorlevel 1 goto error

REM Download manga-ocr model weights on first use (triggers download now so it
REM doesn't stall on first overlay launch)
echo.
echo [4/5] Pre-downloading manga-ocr model weights (this may take a few minutes)...
.venv\Scripts\python.exe -c "from manga_ocr import MangaOcr; MangaOcr()"
if errorlevel 1 (
    echo   WARNING: manga-ocr model download failed or was interrupted.
    echo   It will be downloaded automatically on first overlay launch instead.
)

REM Install JMdict dictionary (needed for word lookups in the popup)
echo.
echo [5/5] Installing JMdict offline dictionary...
.venv\Scripts\python.exe -m jp_anki_builder.cli install-dictionary
if errorlevel 1 (
    echo   WARNING: JMdict install failed. Run 'jp-anki-build install-dictionary' manually.
)

echo.
echo === Done! ===
echo.
echo To launch the overlay standalone:
echo   .venv\Scripts\jp-anki-build.exe overlay
echo.
echo To launch the full GUI (which includes overlay controls):
echo   .venv\Scripts\python.exe manual_tests\launch_gui.py
echo.
goto end

:error
echo.
echo === ERROR: Installation failed. See output above. ===
exit /b 1

:end
