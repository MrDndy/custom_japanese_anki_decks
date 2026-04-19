# Project Tasks

## Instructions for Claude Code

When asked to "work on the next pending task":
1. Find the first task with status `[pending]` below
2. Change its status to `[in-progress]`
3. Read the relevant existing source files before making changes
4. Implement the task following CLAUDE.md guidelines
5. Run tests (`python -m pytest -q`) to verify
6. Verify the specific acceptance criteria listed for the task
7. Change the status to `[done]`
8. Briefly summarize what was changed

---

## Phase 4 — Dictionary Expansion, Subtitle Mining, GUI, and Packaging

**Goal:** Expand the dictionary ecosystem with Yomichan import, add video subtitle mining, build a unified GUI application window with visual review panel and settings, and package the application for Windows distribution.

**Key constraint:** All existing workflows (CLI batch, CLI realtime overlay) must continue working unchanged. The GUI is an additional interface, not a replacement for the CLI.

---

### Task 4.01: Create Yomichan dictionary format parser [done]

Create `src/jp_anki_builder/yomichan_dict.py` — a parser for Yomichan/Yomitan-format dictionary ZIP files.

Yomichan dictionary format:
- A ZIP archive containing JSON files
- `index.json` — dictionary metadata: `{"title": "...", "format": 3, "revision": "..."}`
- `term_bank_N.json` — term entries, each an array: `[expression, reading, definitionTags, rules, score, [glossary...], sequence, termTags]`
- `tag_bank_N.json` — tag definitions: `[name, category, order, notes, score]`
- Optionally `kanji_bank_N.json` — kanji entries (lower priority)

```python
@dataclass
class YomichanEntry:
    expression: str
    reading: str
    meanings: list[str]         # flattened glossary text
    tags: list[str]             # definition tags
    score: int                  # popularity/frequency score
    rules: str                  # inflection rules (e.g., "v5", "vs")

@dataclass
class YomichanDictionary:
    title: str
    revision: str
    entries: dict[str, list[YomichanEntry]]  # keyed by expression for fast lookup
    
    @classmethod
    def from_zip(cls, zip_path: Path) -> YomichanDictionary:
        """Parse a Yomichan-format ZIP file."""
        ...
    
    def lookup(self, word: str) -> list[YomichanEntry]:
        """Look up a word. Returns all matching entries."""
        ...
```

Key parsing considerations:
- Glossary entries can be strings OR structured content objects (dicts with `"type": "structured-content"`). For structured content, extract the text recursively. For string glossaries, use directly.
- Multiple `term_bank_N.json` files may exist (term_bank_1.json, term_bank_2.json, etc.) — parse all of them.
- Tag banks define tags referenced by term entries — parse and resolve them.
- Handle both Yomichan format version 3 (most common) and version 1/2 if straightforward.

**Files to read first:** `dictionary.py` (existing dictionary patterns), `dict_install.py`
**Files to create:** `yomichan_dict.py`
**Acceptance:**
- Can parse a real Yomichan dictionary ZIP (e.g., JMdict for Yomitan, freely available)
- `YomichanDictionary.from_zip()` extracts title, revision, and all term entries
- `lookup("食べる")` returns entries with expression, reading, meanings, tags
- Structured content glossaries are flattened to plain text
- Multiple term banks are merged correctly
- Invalid/corrupt ZIP files produce clear error, not crash
- `python -m pytest -q` passes
- Add tests with a minimal synthetic Yomichan ZIP fixture (index.json + one term_bank)

---

### Task 4.02: Integrate Yomichan dictionaries into lookup pipeline [done]

Create a dictionary provider that wraps `YomichanDictionary` behind the same interface as the existing dictionary providers in `dictionary.py`, and integrate it into the lookup chain.

```python
# In dictionary.py or a new file
class YomichanDictionaryProvider:
    """Dictionary provider backed by imported Yomichan dictionaries."""
    
    def __init__(self, dict_dir: Path):
        """Load all Yomichan dictionaries from a directory."""
        self._dicts: list[YomichanDictionary] = []
        # Load each .zip in dict_dir
        ...
    
    def lookup(self, word: str, exact_match: bool = False):
        """Look up a word across all loaded Yomichan dictionaries.
        Returns dict with 'reading' and 'meanings' matching existing provider format."""
        ...
```

Integration points:
- Add Yomichan as a layer in the lookup cascade: offline (JMdict) → Yomichan dictionaries → online (jisho)
- Yomichan dictionaries are loaded from `data/dictionaries/yomichan/` — any `.zip` file in that directory is auto-loaded
- Update `build_offline_dictionary()` or create a new composite factory that chains JMdict + Yomichan
- Add a CLI command for importing: `jp-anki-build install-yomichan-dict --file path/to/dict.zip` — copies the ZIP to `data/dictionaries/yomichan/` and validates it

Also integrate into `LookupService` so the real-time overlay benefits from Yomichan dictionaries too.

**Files to read first:** `dictionary.py` (lookup interface, factories, `WordExistsCache`), `lookup_service.py`, `cli.py`
**Files to create/modify:** `dictionary.py` (add YomichanDictionaryProvider + composite lookup), `cli.py` (add install-yomichan-dict command), `lookup_service.py` (use composite dictionary)
**Acceptance:**
- `jp-anki-build install-yomichan-dict --file jmdict_yomitan.zip` copies and validates the dictionary
- Yomichan dictionaries in `data/dictionaries/yomichan/` are auto-loaded alongside JMdict
- Words found in Yomichan but not JMdict are now discovered during lookup
- Existing JMdict-only workflow unchanged when no Yomichan dicts are installed
- Real-time overlay uses Yomichan dictionaries
- Batch pipeline uses Yomichan dictionaries
- `python -m pytest -q` passes
- Add test that composite lookup finds a word in Yomichan fallback when JMdict misses

---

### Task 4.03: Add soft subtitle extraction from video files [done]

Create `src/jp_anki_builder/subtitle_extractor.py` — extracts Japanese subtitle text from video files (MKV, MP4) and feeds it into the vocabulary pipeline, bypassing OCR entirely.

```python
@dataclass
class SubtitleLine:
    text: str
    start_ms: int
    end_ms: int
    
@dataclass 
class SubtitleTrack:
    language: str          # e.g., "jpn", "ja"
    format: str            # e.g., "ass", "srt", "ssa"
    lines: list[SubtitleLine]

class SubtitleExtractor:
    """Extracts subtitle tracks from video files."""
    
    @staticmethod
    def detect_tracks(video_path: Path) -> list[dict]:
        """Use ffprobe to list subtitle tracks with language metadata."""
        ...
    
    @staticmethod
    def extract_track(video_path: Path, track_index: int) -> SubtitleTrack:
        """Extract a specific subtitle track using pysubs2."""
        ...
    
    @staticmethod
    def extract_japanese_track(video_path: Path) -> SubtitleTrack | None:
        """Auto-detect and extract the Japanese subtitle track."""
        ...
```

Pipeline integration:
- Add a CLI command: `jp-anki-build scan-subs --video path/to/video.mkv` that extracts Japanese subtitles and runs them through the tokenize → normalize → review → build pipeline
- Subtitle text lines are concatenated and processed as raw text (same as OCR output)
- This bypasses OCR entirely — extracted text goes directly into normalization
- scan.json records should indicate `"ocr_mode": "subtitle"` and include timing metadata

Detection strategy:
- Use `ffprobe` (via subprocess) to list subtitle tracks and their language tags
- Auto-select tracks tagged `jpn`, `ja`, or `Japanese`
- If multiple Japanese tracks exist, prefer text-based (SRT/ASS) over bitmap-based (PGS/VobSub)
- Use `pysubs2` to parse the extracted subtitle content

**Files to read first:** `scan.py`, `format_handlers.py`, `cli.py`, `pipeline.py`
**Files to create:** `subtitle_extractor.py`
**Files to modify:** `cli.py` (add `scan-subs` command), `scan.py` or `pipeline.py` (subtitle-aware scan path)
**Dependencies to add to pyproject.toml:** `pysubs2` (required for subtitle parsing)
**Acceptance:**
- `jp-anki-build scan-subs --video anime_episode.mkv` extracts Japanese subtitles and produces scan.json
- Full pipeline works: `jp-anki-build run-subs --video anime_episode.mkv` → scan → review → build → deck.apkg
- Auto-detects Japanese subtitle track by language tag
- Graceful error when no Japanese subtitles found
- Graceful error when ffprobe not installed (clear message to install FFmpeg)
- pysubs2 handles SRT, ASS/SSA formats
- Bitmap subtitle tracks (PGS) are skipped with a message suggesting OCR workflow instead
- `python -m pytest -q` passes
- Add tests with mock ffprobe output and a minimal SRT fixture

---

### Task 4.04: Create main application window shell [done]

Create `src/jp_anki_builder/gui/` package with `main_window.py` — the primary PySide6 application window that serves as the unified entry point for all workflows.

```python
class MainWindow(QMainWindow):
    """Main application window with tabs for batch processing, realtime overlay, and settings."""
    
    def __init__(self, data_dir: str = "data"):
        ...
        # Tab widget with three tabs:
        # 1. Batch Processing — source selector, pipeline controls, progress
        # 2. Real-Time Overlay — launch/stop overlay, status, session history
        # 3. Settings — all config options
```

**Batch Processing tab layout:**
- Source input: drag-and-drop zone + file browser button (accepts directories, CBZ, CBR, PDF, EPUB, MKV)
- Source/run_id fields (auto-inferred from path, editable)
- Deck name configuration (series name, volume, chapter fields)
- OCR engine selector dropdown (sidecar, manga-ocr, tesseract)
- Detector mode dropdown (none, paddleocr)
- "Scan" / "Review" / "Build" / "Run All" buttons
- Progress bar + log output area
- Status bar showing current stage and word counts

**Real-Time Overlay tab:**
- "Launch Overlay" / "Stop Overlay" button
- Capture backend selector (dxcam, mss)
- ROI size configuration
- Hotkey display/configuration
- Session history (list of past sessions with export dates)

**Settings tab:**
- All ProjectDefaults keys as form fields
- Dictionary management (installed dictionaries list, install button)
- AnkiConnect settings (enable/disable, port)
- Save/reset buttons

Reuse Phase 3 widget patterns: dark frames, consistent styling. The window should work on its own — it does NOT require the overlay to be running.

**Files to read first:** `realtime/overlay.py` and `realtime/buffer_panel.py` (widget patterns), `project_config.py`, `cli.py`
**Files to create:** `gui/__init__.py`, `gui/main_window.py`
**Acceptance:**
- Window opens with three tabs
- Batch tab has all listed controls (non-functional wiring is OK for this task — wiring is Task 4.06)
- Realtime tab has launch button and config
- Settings tab shows all config keys with current values
- Drag-and-drop zone accepts files
- Window follows existing visual style (dark semi-transparent frames from Phase 3)
- `python -m pytest -q` passes

---

### Task 4.05: Create review panel widget [done]

Create `src/jp_anki_builder/gui/review_panel.py` — a visual review interface for approving/rejecting candidate words from a scan, replacing the CLI-only review workflow with an interactive GUI.

```python
class ReviewPanel(QWidget):
    """Interactive word review interface for batch scan results."""
    
    review_completed = Signal(list)  # emits list of approved words
    
    def load_candidates(self, scan_path: Path, source: str):
        """Load candidates from scan.json and display for review."""
        ...
    
    def _build_word_table(self, candidates: list[dict]):
        """Build scrollable table with columns:
        - Checkbox (approve/reject)
        - Surface form
        - Dictionary form (lemma)
        - Reading
        - Meaning (from dictionary lookup)
        - Confidence (from normalization)
        - JLPT level
        - Flags (OOV, SFX, low-confidence)
        """
        ...
```

Features:
- Sortable columns (click header to sort by confidence, JLPT level, etc.)
- Bulk actions: "Approve All", "Reject All OOV", "Approve N3+", "Reject SFX"
- Search/filter bar (filter visible words by text)
- Color coding: green for high-confidence dictionary-validated, yellow for deinflection-validated, red for surface-fallback/OOV
- "Add to known words" button — adds selected rejected words to `known_words.txt`
- Word count summary: "X of Y candidates approved"
- Loads data from `scan.json` (candidates + normalized_candidates with confidence) and cross-references with `seen_words.json` and `known_words.txt`
- Emits `review_completed` signal with the approved word list

This panel is embedded in the Batch Processing tab of the main window. It replaces the CLI `--exclude` workflow with a visual alternative — the CLI review still works for users who prefer it.

**Files to read first:** `review.py`, `filtering.py`, `scan.py` (scan.json format), `realtime/buffer_panel.py` (widget patterns), `lookup_service.py`
**Files to create:** `gui/review_panel.py`
**Acceptance:**
- Loads candidates from a scan.json file and displays in a table
- Each row shows surface, lemma, reading, meaning, confidence, JLPT, flags
- Checkboxes for individual approve/reject
- Bulk action buttons work (approve all, reject OOV, etc.)
- Search bar filters the visible list
- Color coding by confidence tier
- "Add to known words" writes to known_words.txt
- `review_completed` signal emits the approved word list
- `python -m pytest -q` passes

---

### Task 4.06: Wire main window to pipeline [done]

Connect the main window UI controls to the actual pipeline operations. This is the integration task that makes the Batch tab functional.

Wiring:
- "Run All" button → calls `Pipeline.run_all()` in a QThread worker, updates progress bar
- "Scan" button → calls `Pipeline.scan()` in a QThread, then loads results into ReviewPanel
- After scan, ReviewPanel shows candidates for interactive review
- "Build" button → takes approved words from ReviewPanel, calls `Pipeline.build()`
- Progress bar updates during scan (per-image progress)
- Log output area shows pipeline logging messages (redirect logger to a QTextEdit)
- Source path from drag-and-drop / file browser populates the source/run_id fields via path_inference
- Settings tab "Save" button writes to project_config
- "Launch Overlay" button starts OverlayApp (or just the overlay components)
- Subtitle input: when user selects a video file, route to subtitle extraction pipeline

All pipeline operations must run in QThread workers — never block the main thread.

**Files to read first:** `pipeline.py`, `gui/main_window.py`, `gui/review_panel.py`, `project_config.py`, `realtime/app.py`, `subtitle_extractor.py`
**Files to modify:** `gui/main_window.py`
**Files to create:** `gui/workers.py` (QThread workers for pipeline stages)
**Acceptance:**
- Selecting a directory/file and clicking "Run All" executes the full pipeline with progress feedback
- Scan results populate the review panel for interactive review
- Build uses the review panel's approved words
- Pipeline errors display in the log area (not silent crashes)
- All pipeline operations run in worker threads (UI stays responsive)
- Drag-and-drop populates source fields correctly
- Settings changes are persisted
- "Launch Overlay" opens the realtime overlay
- `python -m pytest -q` passes

---

### ⏸️ CHECKPOINT — GUI Review

**When Tasks 4.01–4.06 are all `[done]`**, output this message:

```
⏸️ CHECKPOINT: Ready for GUI review

Tasks 4.01–4.06 are complete. The main application window, review panel, and pipeline
integration are implemented alongside Yomichan dictionary support and subtitle extraction.

Next steps:
1. Manually test the full GUI workflow:
   - Launch main window, drag a manga CBZ onto the batch tab, run scan, review words
     in the review panel, build a deck
   - Test Yomichan dictionary: install a dictionary, verify lookups include it
   - Test subtitle extraction: point at a video with Japanese subs
   - Launch realtime overlay from the GUI
2. Switch to Opus (/model opus) and run a targeted review:

   "Read CLAUDE.md. Review src/jp_anki_builder/gui/ and src/jp_anki_builder/yomichan_dict.py
   and src/jp_anki_builder/subtitle_extractor.py. Focus on: threading safety (no main thread
   blocking), dictionary integration correctness (Yomichan entries merge properly with JMdict),
   subtitle extraction error handling, review panel data flow (scan.json → table → approved
   list → build), and settings persistence. Report issues by severity."

3. Fix any issues found, then resume with the next pending task.
```

**Do not proceed to Task 4.07 until the developer resumes.**

---

### Task 4.07: Add CLI command for GUI launch [done]

Add a `jp-anki-build gui` command that launches the main application window. Similar to how `overlay` is implemented — lazy PySide6 import, graceful error if not installed.

```python
@app.command()
def gui(data_dir: str = "data"):
    """Launch the graphical application."""
    try:
        from jp_anki_builder.gui.app import launch_gui
    except ImportError:
        print("GUI requires PySide6. Install with: pip install PySide6")
        raise SystemExit(1)
    launch_gui(data_dir=data_dir)
```

Create `src/jp_anki_builder/gui/app.py` — minimal entry point that creates QApplication and MainWindow:

```python
def launch_gui(data_dir: str = "data") -> int:
    app = QApplication.instance() or QApplication(sys.argv)
    window = MainWindow(data_dir=data_dir)
    window.show()
    return app.exec()
```

**Files to read first:** `cli.py` (overlay command pattern), `realtime/app.py` (QApplication handling)
**Files to create:** `gui/app.py`
**Files to modify:** `cli.py` (add `gui` command)
**Acceptance:**
- `jp-anki-build gui` launches the main window
- Missing PySide6 produces clear error message
- Existing CLI commands still work without PySide6
- Clean shutdown on window close
- `python -m pytest -q` passes

---

### Task 4.08: Windows packaging with PyInstaller [done]

Create a PyInstaller spec and build configuration that packages the application into a distributable Windows executable.

Create `packaging/` directory with:
- `build.py` or `build.bat` — build script that invokes PyInstaller
- `jp_anki_builder.spec` — PyInstaller spec file
- `README.md` — packaging instructions

Key packaging considerations:
- Entry point: `jp-anki-build` CLI (users can run `jp-anki-build gui`, `jp-anki-build overlay`, or any CLI command)
- Bundle: Python runtime, all dependencies, manga-ocr model files, SudachiPy dictionary
- Exclude: PaddleOCR (too large — document as optional separate install), test files
- Hidden imports: PySide6 plugins, fugashi/MeCab dictionaries, SudachiPy backends
- Data files: include `data/dictionaries/` template structure
- Icon: create a simple application icon (or use a placeholder)
- Output: single directory distribution (not one-file — manga-ocr model is too large for one-file)

Also create a minimal `NSIS` or `Inno Setup` script (or document how to use one) for creating a Windows installer `.exe` from the PyInstaller output. If creating the actual installer script is too complex, document the steps clearly instead.

**Files to read first:** `pyproject.toml` (dependencies), `cli.py` (entry point)
**Files to create:** `packaging/build.py`, `packaging/jp_anki_builder.spec`, `packaging/README.md`
**Acceptance:**
- `python packaging/build.py` produces a working `dist/jp-anki-build/` directory
- `dist/jp-anki-build/jp-anki-build.exe gui` launches the GUI
- `dist/jp-anki-build/jp-anki-build.exe overlay` launches the overlay
- `dist/jp-anki-build/jp-anki-build.exe run --images ./test` runs the batch pipeline
- Application icon is visible
- README documents: how to build, what's included, what needs separate install (PaddleOCR)
- `python -m pytest -q` passes (packaging doesn't break test suite)

---

### Task 4.09: Write tests for all Phase 4 functionality [done]

Ensure comprehensive test coverage for all Phase 4 modules.

Test categories:
- **YomichanDictionary**: parse minimal ZIP fixture, lookup, structured content flattening, multi-bank merge, invalid ZIP handling
- **YomichanDictionaryProvider**: composite lookup (JMdict miss → Yomichan hit), install-yomichan-dict command
- **SubtitleExtractor**: mock ffprobe output, SRT parsing, Japanese track auto-detection, missing ffprobe handling
- **ReviewPanel**: load candidates from fixture scan.json, bulk actions, search filter, approve/reject flow (mark `@pytest.mark.gui`)
- **MainWindow**: tab switching, drag-and-drop acceptance (mark `@pytest.mark.gui`)
- **Pipeline workers**: QThread lifecycle, signal emission (mark `@pytest.mark.gui`)
- **Integration**: Yomichan dict install → lookup → batch pipeline → deck includes Yomichan-sourced word
- **Integration**: Subtitle file → scan-subs → review → build → deck

Mark GUI tests with `@pytest.mark.gui`. Verify all Phase 1–3 tests still pass.

**Files to create:** `tests/test_yomichan_dict.py`, `tests/test_subtitle_extractor.py`, `tests/test_gui_review_panel.py`, `tests/test_gui_main_window.py`, `tests/integration/test_yomichan_pipeline.py`, `tests/integration/test_subtitle_pipeline.py`
**Acceptance:**
- All non-GUI tests pass: `python -m pytest -q -m "not gui"`
- GUI tests pass locally when display is available
- All Phase 1, 2, and 3 tests still pass
- `python -m pytest -q` reports 0 failures (GUI tests skipped cleanly in headless)

---

## Phase Completion Protocol

**When ALL tasks above are marked `[done]`**, output the following message exactly:

```
✅ PHASE 4 COMPLETE

All tasks are done and tests pass.

Next steps for the developer:
1. Run the Opus code review using REVIEW_CHECKLIST.md
2. Fix any issues found in the review
3. The core application is now feature-complete. Future work (Phase 5+) may include:
   - AI sense ranking integration
   - Textractor/LunaTranslator text hooking for visual novels
   - macOS port
   - Full user documentation
   - iOS companion app
4. Return to the Claude.ai web UI project conversation to discuss next priorities.

Do NOT proceed to Phase 5 topics — the scope has not been defined yet.
```

**Do not attempt to define or start Phase 5 tasks on your own.**
