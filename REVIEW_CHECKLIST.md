# Phase 4 — Opus Code Review Checklist (Final Review)

> **Context:** One intermediate Opus review was conducted at the GUI checkpoint (after Task 4.06)
> covering the main window, review panel, Yomichan support, and subtitle extraction.
>
> This final review focuses on Tasks 4.07–4.09 (CLI command, packaging, tests) and a full
> end-to-end verification that all workflows function correctly together.
>
> **When to use:** After all Phase 4 tasks are marked [done] in TASKS.md, switch to Opus
> (`/model opus`) and give it this prompt:
>
> "Read CLAUDE.md and REVIEW_CHECKLIST.md. An intermediate Opus review was done at the GUI
> checkpoint (after 4.06). Focus this review on Tasks 4.07–4.09 (CLI gui command, packaging,
> tests) plus a full-application integration check. Verify all four workflows work: batch CLI,
> realtime overlay, GUI batch, and subtitle extraction. Report issues grouped by severity with
> specific file:line references."

---

## Backward Compatibility — CRITICAL (Check First)

- [ ] `jp-anki-build run --images ./screenshots/` still works (original screenshot workflow)
- [ ] `jp-anki-build run --images ./manga.cbz --detector-mode paddleocr` still works (Phase 2)
- [ ] `jp-anki-build overlay` still works (Phase 3)
- [ ] `jp-anki-build scan`, `review`, `build` subcommands all work independently
- [ ] `--dry-run`, `--resume` still work
- [ ] Config system handles all keys from Phases 1–4
- [ ] All Phase 1, 2, and 3 tests pass without modification
- [ ] Deck output format unchanged across all workflows

## Licensing Compliance

- [ ] No GPL/AGPL imports anywhere
- [ ] `pysubs2` is MIT — confirmed
- [ ] PyInstaller is GPL but it's a build tool, not a shipped runtime dependency — acceptable
- [ ] No new licensing concerns in pyproject.toml
- [ ] JMdict attribution present in about/credits if GUI has one

## Yomichan Dictionary Parser

- [ ] `YomichanDictionary.from_zip()` handles real-world Yomichan dictionary ZIPs
- [ ] Multiple `term_bank_N.json` files are all parsed and merged
- [ ] Structured content glossaries (dicts with `"type": "structured-content"`) are flattened to text
- [ ] String glossaries are used directly
- [ ] Tag banks are parsed and available
- [ ] Score/frequency data is preserved
- [ ] Invalid ZIP produces clear error, not crash
- [ ] Empty dictionary (valid ZIP, no entries) handled gracefully

## Yomichan Integration

- [ ] `YomichanDictionaryProvider` follows existing dictionary provider interface (has `lookup()` returning `{"reading": ..., "meanings": [...]}`)
- [ ] Auto-loads all `.zip` files from `data/dictionaries/yomichan/`
- [ ] Composite lookup order: JMdict → Yomichan → online (Jisho)
- [ ] Words found only in Yomichan are correctly surfaced in batch pipeline
- [ ] Words found only in Yomichan are correctly surfaced in real-time overlay
- [ ] `WordExistsCache` works correctly with composite dictionary
- [ ] `install-yomichan-dict` command validates the ZIP before copying
- [ ] Missing Yomichan directory handled gracefully (no crash when `data/dictionaries/yomichan/` doesn't exist)
- [ ] No Yomichan dicts installed → system works exactly as before (no empty-list errors)

## Subtitle Extraction

- [ ] `SubtitleExtractor.detect_tracks()` calls ffprobe correctly and parses JSON output
- [ ] Auto-selects tracks tagged `jpn`, `ja`, or `Japanese`
- [ ] Prefers text-based subs (SRT/ASS) over bitmap (PGS/VobSub)
- [ ] pysubs2 parses SRT and ASS/SSA correctly
- [ ] Missing ffprobe produces clear error message (not stack trace)
- [ ] No Japanese subtitle track → clear message
- [ ] Bitmap-only subtitles → message suggesting OCR workflow instead
- [ ] `scan-subs` command produces valid scan.json
- [ ] `run-subs` command runs full pipeline end-to-end
- [ ] Timing metadata (start_ms, end_ms) preserved in scan records
- [ ] Subtitle text feeds into the same normalization/review/build pipeline as OCR text

## Main Window GUI

- [ ] Three tabs present: Batch, Real-Time, Settings
- [ ] Drag-and-drop zone accepts directories, CBZ, CBR, PDF, EPUB, MKV files
- [ ] Path inference populates source/run_id fields correctly
- [ ] OCR engine and detector mode dropdowns work
- [ ] "Run All" executes pipeline in QThread (UI stays responsive)
- [ ] Progress bar updates during scan
- [ ] Log area shows pipeline output
- [ ] Pipeline errors display in log area (not silent)
- [ ] "Launch Overlay" opens the realtime overlay
- [ ] Settings tab shows all config keys with current values
- [ ] Settings "Save" persists to project_config
- [ ] Clean shutdown — no hanging worker threads

## Review Panel

- [ ] Loads candidates from scan.json correctly
- [ ] Table shows: surface, lemma, reading, meaning, confidence, JLPT, flags
- [ ] Checkboxes for individual approve/reject work
- [ ] Bulk actions: "Approve All", "Reject OOV", "Approve N3+", "Reject SFX" all work
- [ ] Search bar filters visible rows
- [ ] Color coding: green (dictionary-validated), yellow (deinflection), red (surface-fallback/OOV)
- [ ] "Add to known words" writes to correct known_words.txt
- [ ] `review_completed` signal emits correct approved word list
- [ ] Approved words flow into build stage correctly
- [ ] Sortable columns work

## CLI and GUI Launch

- [ ] `jp-anki-build gui` launches the main window
- [ ] `jp-anki-build overlay` still launches the overlay independently
- [ ] Missing PySide6 → clear error on `gui` and `overlay` commands
- [ ] All non-GUI CLI commands work without PySide6 installed
- [ ] PySide6 is NOT imported until `gui` or `overlay` is invoked (lazy import)
- [ ] Clean shutdown on window close for both `gui` and `overlay`

## Windows Packaging

- [ ] PyInstaller spec file exists and is documented
- [ ] Build script runs without manual intervention
- [ ] Built executable launches GUI correctly
- [ ] Built executable runs batch CLI correctly
- [ ] Built executable runs overlay correctly
- [ ] manga-ocr model files are bundled (or documented how to add them)
- [ ] SudachiPy dictionary is bundled
- [ ] Hidden imports are covered (PySide6 plugins, fugashi, etc.)
- [ ] README documents what's included, what's optional, how to build
- [ ] Application has an icon

## Threading Safety

- [ ] All pipeline operations in the GUI run in QThread workers
- [ ] No main thread blocking during scan, review lookup, or build
- [ ] Worker threads can be cancelled (e.g., user closes window during scan)
- [ ] No race conditions between review panel updates and worker completion
- [ ] Overlay launch from GUI doesn't conflict with main window event loop

## Code Quality

- [ ] All new files use `from __future__ import annotations`
- [ ] All public functions have type hints
- [ ] All new modules have module-level docstrings
- [ ] No bare `except:` — exceptions are specific
- [ ] Logging via `logging.getLogger(__name__)`
- [ ] New config keys in `VALID_KEYS` with correct type coercion
- [ ] PySide6 behind `try/except ImportError` in CLI
- [ ] GUI tests marked `@pytest.mark.gui`
- [ ] Factory functions follow `build_*()` naming

## Test Coverage

- [ ] Yomichan parser: synthetic ZIP fixture, lookup, structured content, multi-bank, invalid ZIP
- [ ] Yomichan integration: composite lookup, install command, fallback chain
- [ ] Subtitle extraction: mock ffprobe, SRT fixture, auto-detection, missing ffprobe
- [ ] Review panel: load scan.json, bulk actions, search, approve flow (GUI marker)
- [ ] Main window: tab switching, drag-and-drop (GUI marker)
- [ ] Pipeline workers: QThread lifecycle (GUI marker)
- [ ] Integration: Yomichan + batch pipeline end-to-end
- [ ] Integration: subtitle + full pipeline end-to-end
- [ ] All Phase 1–3 tests pass
- [ ] `python -m pytest -q -m "not gui"` reports 0 failures

---

## Review Output Format

```
### CRITICAL: [description]
**File:** src/jp_anki_builder/gui/main_window.py:142
**Issue:** [specific problem]
**Fix:** [suggested fix]

### MODERATE: [description]
**File:** src/jp_anki_builder/yomichan_dict.py:67
**Issue:** [specific problem]
**Fix:** [suggested fix]

### MINOR: [description]
**File:** src/jp_anki_builder/subtitle_extractor.py:30
**Issue:** [specific problem]
**Fix:** [suggested fix]
```

After the review, summarize:
- Total issues by severity
- Top 3 highest-priority fixes
- Overall assessment: application ready for release, or needs another pass?
