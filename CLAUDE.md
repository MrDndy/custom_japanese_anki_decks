# JP Anki Builder — Architecture Guide for Claude Code

> This file provides the architectural context needed to work on this project.
> For the full research document, see `docs/unified-architecture.md`.
> For current tasks, see `TASKS.md`.

## Project Overview

Desktop application with a CLI batch pipeline and a real-time screen overlay that extracts Japanese vocabulary from manga, games, and video subtitles, then generates Anki flashcard decks.

- **Batch workflow** (Phase 1–2): Manga pages/CBZ/PDF/EPUB → detect regions → OCR → tokenize + normalize → review/filter → dictionary enrich → export .apkg
- **Real-time workflow** (Phase 3): Screen capture → OCR near cursor → popup dictionary → hotkey adds to buffer → export .apkg
- **GUI application** (Phase 4, current): Main window unifying batch + realtime, visual review panel, settings, and packaging

## Codebase Map

**Package:** `src/jp_anki_builder/`
**CLI entry:** `jp-anki-build` (Typer-based, defined in pyproject.toml)
**Pipeline:** `scan` → `review` → `build` (orchestrated by `pipeline.py`, CLI in `cli.py`)
**Overlay:** `jp-anki-build overlay` (launches PySide6 real-time screen OCR)

### Module Responsibilities

| Module | Role |
|--------|------|
| `cli.py` | Typer CLI: `run`, `scan`, `review`, `build`, `config`, `install-dictionary`, `migrate-dictionary`, `overlay` |
| `pipeline.py` | `Pipeline` class orchestrating scan→review→build |
| `scan.py` | OCR + region detection + tokenize + normalize, writes scan.json |
| `review.py` | Filters particles/known/seen/SFX/furigana, writes review.json with confidence |
| `build.py` | Dictionary enrichment + genanki deck generation + vocab_db recording |
| `cards.py` | `build_deck_name()`, `build_note_fields()`, `build_genanki_model()` — single source of truth for Anki card model |
| `ocr.py` | `OcrProvider` Protocol + Sidecar/MangaOcr/Tesseract + factory |
| `protocols.py` | `RegionDetector` Protocol + `DetectedRegion` dataclass |
| `region_detectors/` | PaddleOcrDetector, NullDetector + factory |
| `format_handlers.py` | CBZ/CBR/PDF/EPUB extraction + `PageResult` + spread detection |
| `tokenize.py` | fugashi (MeCab) tokenization |
| `normalization.py` | `Normalizer` Protocol + `SudachiNormalizer` (default) + `NormalizedCandidate` |
| `deinflect.py` | Yomitan-style deinflection engine, 100+ rules |
| `ocr_corrections.py` | Confusable character substitution |
| `dictionary.py` | OfflineJson/OfflineSqlite/Jisho/Null dictionaries + `WordExistsCache` + factories |
| `filtering.py` | Particle + SFX + furigana filtering |
| `vocab_db.py` | Central SQLite vocabulary database at `data/vocabulary.db` |
| `enrich.py` | `enrich_word()` — reading + meanings lookup |
| `jlpt.py` | `JlptLookup` — JLPT level data |
| `lookup_service.py` | `LookupService` — single-call tokenize + normalize + filter + lookup for real-time use |
| `screen_capture.py` | `ScreenCapture` Protocol + DXcam/mss backends |
| `anki_connect.py` | AnkiConnect REST client for live dedup |
| `realtime/` | Real-time overlay package |
| `realtime/ocr_worker.py` | Capture → hash change detection → edge density pre-filter → OCR → LRU cache |
| `realtime/overlay.py` | Transparent click-through popup widget |
| `realtime/buffer_panel.py` | Floating session word list panel |
| `realtime/hotkeys.py` | Global hotkey manager via pynput |
| `realtime/controller.py` | Qt-threaded orchestrator (QThread + QTimer cursor sampling) |
| `realtime/session.py` | Session buffer + deck export |
| `realtime/app.py` | OverlayApp assembly + `_HotkeyBridge` for pynput→Qt marshalling |
| `config.py` | `RunPaths` dataclass |
| `project_config.py` | JSON config system (project + source level) + `ProjectDefaults` |
| `path_inference.py` | Source/run_id inference from directory paths |
| `dedup.py` | `exclude_seen()` helper |
| `dict_install.py` | JMdict dictionary installation |

### Key Patterns

1. **Protocol + factory** — `OcrProvider`, `RegionDetector`, `ScreenCapture`, `Normalizer` all use Protocol + `build_*()` factory
2. **Dictionary providers** — factory pattern in `dictionary.py`, multiple backends behind common interface
3. **PySide6 isolation** — Qt imports inside `try/except ImportError`. CLI commands work without PySide6. Only `overlay` (and future GUI commands) trigger PySide6.
4. **Lazy initialization** — OCR models, dictionaries, QApplication all init on first use, never at import
5. **Config** — `ProjectDefaults` dataclass + `VALID_KEYS` set in `project_config.py`. Two-level JSON (project + source). Extend, don't replace.
6. **Card model** — `build_genanki_model()` in `cards.py` is the single source of truth. Both batch and realtime export use it.
7. **Widget patterns** — Phase 3 established: dark semi-transparent frames, `QScrollArea` for word lists, action buttons. Reuse these patterns for new widgets.

### Data Layout

```
data/
  .jp-anki.json                  # project config
  vocabulary.db                  # cross-source vocab tracking
  dictionaries/
    offline.json or offline.db   # JMdict dictionary
    jlpt_levels.json             # JLPT data
    yomichan/                    # Phase 4: imported Yomichan dictionaries
  <source>/
    .jp-anki.json                # source config
    known_words.txt              # user exclusion list
    seen_words.json              # dedup tracking
    <run_id>/
      scan.json, review.json, build.json, deck.apkg, word_cache.json, debug/
```

## Licensing Rule — CRITICAL

**All shipped dependencies must be permissively licensed (MIT, Apache-2.0, LGPL, BSD).**

- ✅ PySide6 (LGPL), DXcam (MIT), pynput (LGPL), pdfplumber (MIT), pypdfium2 (Apache-2.0/BSD-3)
- ✅ manga-ocr (Apache-2.0), PaddleOCR (Apache-2.0), SudachiPy (Apache-2.0), fugashi (MIT), genanki (MIT)
- ✅ pysubs2 (MIT) — for subtitle extraction
- ❌ NEVER: comic-text-detector (GPL-3.0), mokuro (GPL-3.0), PyMuPDF/fitz (AGPL)

## Phase 4 Focus

Phase 4 adds four capabilities in this order:
1. **Yomichan dictionary import** — parse Yomichan-format ZIP dictionaries and integrate as a lookup provider alongside JMdict
2. **Soft subtitle extraction** — extract Japanese subtitle tracks from video files (MKV/MP4) for direct text processing without OCR
3. **Main application window** — PySide6 GUI that unifies batch workflow, real-time overlay launch, review panel, and settings
4. **Windows packaging** — distributable installer/executable

## Coding Conventions (Match Existing Style)

- Python 3.12+
- `from __future__ import annotations` at top of every module
- Type hints on all functions
- `@dataclass` for data structures, `Protocol` for interfaces
- Tests in `tests/` using pytest, classes with `Test` prefix
- Typer for CLI commands
- Logging via `logging.getLogger(__name__)`
- Factory functions named `build_*()` 
- Qt threading: QThread with signals/slots for workers
- PySide6 behind `try/except ImportError` — CLI must work without it
- GUI tests marked `@pytest.mark.gui` and skippable in headless CI

## What NOT to Do

- Do not replace the JSON config system
- Do not restructure the data/ directory layout
- Do not add GPL/AGPL dependencies
- Do not create a second Anki card model — use `build_genanki_model()` from `cards.py`
- Do not bypass `dictionary.py` factories — new dictionary sources go through the factory pattern
- Do not block the main (UI) thread with I/O, OCR, or dictionary lookups
- Do not make PySide6 required for CLI commands (scan, review, build, run)
- Do not put model/dictionary loading at import time
