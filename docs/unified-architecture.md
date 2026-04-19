# Japanese OCR-to-Anki Application — Unified Architecture Document

**Version:** 1.1
**Date:** March 14, 2026
**Status:** Pre-development reference — consolidates findings from dual independent research efforts
**Licensing stance:** Permissive. GPL components used as benchmarks and reference only, never as shipped dependencies.

---

## 1. Project Vision

A Windows desktop application that extracts Japanese vocabulary from visual media (manga, video games, video subtitles) and converts it into Anki flashcard decks. Two primary workflows:

**Workflow A — Batch Processing:** User supplies manga pages, PDFs, CBZ/CBR archives, or EPUB files. The application automatically detects text regions, runs OCR, tokenizes and lemmatizes words, looks up definitions, and generates an Anki deck with customizable deck/subdeck hierarchy.

**Workflow B — Real-Time Screen OCR:** A persistent overlay captures a region of the screen (or a specific application window), runs OCR on Japanese text near the cursor, and displays a popup with readings and definitions. A hotkey adds words to a session buffer. At the end of a session, the buffer is exported as an Anki deck using the same backend as Workflow A.

Both workflows share a common NLP pipeline (tokenize → deconjugate → dictionary lookup → deduplicate → export) and a common vocabulary tracking database.

---

## 2. High-Level Architecture

The system is organized in four layers. The core pipeline is CLI-invocable and GUI-independent, enabling headless batch processing. The GUI layer adds the overlay, review panel, and settings interface on top.

```
┌──────────────── GUI Layer (PySide6) ─────────────────┐
│  Transparent Overlay    │  Review/Filter Panel        │
│  (hover popup, hotkeys) │  (approve/reject candidates)│
│  Session Buffer Panel   │  Settings & Config          │
│  Deck Manager           │                             │
├──────────────── Core Pipeline (CLI-invocable) ───────┤
│                                                       │
│  Ingest → Detect Regions → OCR → Tokenize →          │
│  Deconjugate → Dictionary Lookup → Deduplicate →     │
│  Quality Filter → Review → Export                     │
│                                                       │
├──────────────── Plugin System ───────────────────────┤
│  OCR Engines        │ Tokenizers    │ Dictionaries    │
│  (manga-ocr,        │ (SudachiPy,   │ (jamdict/JMdict,│
│   MeikiOCR,         │  fugashi/     │  Yomichan-fmt,  │
│   Google Lens,      │  MeCab,       │  jisho fallback)│
│   PaddleOCR,        │  Janome)      │                 │
│   WinRT, owocr)     │               │                 │
├──────────────── State & Data Layer ──────────────────┤
│  SQLite DB          │  TOML Config  │  File Artifacts │
│  (vocab tracking,   │  (per-source  │  (scan.json,    │
│   dedup history,    │   defaults,   │   review.json,  │
│   session state)    │   OCR prefs)  │   deck.apkg)    │
└──────────────────────────────────────────────────────┘
```

### Design Principles

- **Same NLP pipeline for both workflows.** The tokenize → deconjugate → lookup → annotate chain is identical whether fed by batch OCR or real-time screen capture. This avoids duplication and ensures vocabulary consistency.
- **Plugin architecture for swappable components.** OCR engines, tokenizers, and dictionary sources are abstracted behind interfaces. Users can swap backends without modifying core logic.
- **CLI-first core.** Every stage (scan, review, build) is independently invocable from the command line. The GUI is a layer on top, not a prerequisite.
- **File-backed artifacts for auditability.** Each pipeline stage writes intermediate JSON artifacts under `data/<source>/<run_id>/`, enabling inspection, correction, and reruns.
- **Offline by default, cloud-enhanced optionally.** All core functionality works without internet. Cloud OCR (Google Lens) and AI sense-ranking (Gemini/Claude) are opt-in enhancements.

---

## 3. OCR Engine Strategy

### 3.1 Engine Comparison

| Engine | Best For | Accuracy (Manga) | Speed | Offline | License | Notes |
|--------|----------|-------------------|-------|---------|---------|-------|
| **manga-ocr** | Manga, VN dialogue | ★★★★★ | ~200ms GPU, ~800ms CPU | Yes | Apache-2.0 | ViT+GPT-2, trained on manga. Handles vertical, furigana, stylized fonts. Multi-line in single pass. |
| **MeikiOCR** | Game UI text | ★★★★☆ | Fastest (ONNX) | Yes | MIT | Two-model ONNX pipeline. 64-box cap, 48-char line limit. Beta vertical support. |
| **Google Lens** | General Japanese | ★★★★★ | ~300ms (network) | No | Free (reverse-eng.) | Near Cloud Vision quality without API key. Via owocr. |
| **Google Cloud Vision** | Documents, fallback | ★★★★☆ | ~500ms (network) | No | Pay ($1.50/1k) | 1,000 free/month. Async PDF mode. |
| **PaddleOCR (PP-OCRv5)** | Structured docs | ★★★☆☆ | Fast (GPU) | Yes | Apache-2.0 | Good CJK support. Not manga-optimized. Permissive license. |
| **EasyOCR** | Quick prototype | ★★☆☆☆ | Moderate | Yes | Apache-2.0 | Easiest setup. Lower accuracy for Japanese. |
| **Tesseract** | Clean printed text | ★☆☆☆☆ (manga) | Fast | Yes | Apache-2.0 | Severe vertical text bugs. Not recommended for manga/games. |
| **WinRT OCR (OneOCR)** | Windows built-in | ★★★☆☆ | Fast | Yes | N/A | Surprisingly decent. Requires MSIX package identity for distribution. |
| **Apple Vision** | macOS/iOS | ★★★★☆ | Fast | Yes | N/A | Platform-locked. Best local engine on Apple. Future macOS port. |
| **Chrome Screen AI** | Cross-platform local | ★★★★☆ | Fast | Yes | Chromium | Emerging. Accessible via owocr. |

### 3.2 Recommended Engine Selection by Use Case

| Use Case | Primary | Fallback | Rationale |
|----------|---------|----------|-----------|
| Manga batch (Workflow A) | manga-ocr | Google Lens | Best manga accuracy; Lens for stubborn regions |
| Game text real-time (Workflow B) | MeikiOCR (ONNX+GPU) | manga-ocr | Speed-critical; MeikiOCR is fastest for rendered UI text |
| Video subtitles | Extract soft subs first; OCR only for hardcoded | Google Lens | See §3.4 |
| Browser-based manga | manga-ocr | Google Lens | Same as batch but triggered from screen capture |
| Offline-only constraint | manga-ocr | Chrome Screen AI or WinRT | No network dependency |

### 3.3 owocr as the Abstraction Layer

**owocr** unifies 12+ OCR engines under a single Python interface and is the recommended abstraction layer rather than building custom wrappers for each engine. It supports Google Lens, MeikiOCR, manga-ocr, Chrome Screen AI, OneOCR, Apple Live Text, WinRT OCR, EasyOCR, RapidOCR, and more. It also handles clipboard/screen monitoring and image preprocessing.

Integration approach: use owocr as a dependency for engine management, but wrap it behind your own `OcrEngine` interface so you can add custom engines or override behavior without forking owocr.

### 3.4 Subtitle Optimization: Extract Before OCR

For video subtitle mining, always check for extractable subtitle tracks before running OCR. Many subtitle sources are already text data (SRT/ASS/SSA embedded in MKV/MP4).

```
Video file input
  → ffprobe / pysubs2: detect subtitle tracks
  → If soft subs found: extract text directly → skip OCR entirely
  → If hardcoded only: capture subtitle region → OCR pipeline
```

This eliminates OCR errors entirely for soft-subbed content and is a major accuracy and performance win. Use `pysubs2` for extraction and `ffprobe` (via `subprocess`) for track detection.

### 3.5 ONNX Runtime Acceleration

manga-ocr can be exported to ONNX format (`l0wgear/manga-ocr-2025-onnx`) for 2–3× inference speedup via ONNX Runtime with CUDA or DirectML execution providers. This is especially important for the real-time workflow where latency matters. Pre-warm the model at application startup to avoid cold-start delays.

---

## 4. Text Detection & Region Extraction

### 4.1 Manga Text Detection

The text detection stage is responsible for locating speech bubbles, narration boxes, captions, and other text-bearing regions on a manga page before passing cropped regions to OCR. This separation is critical: the detector determines what the OCR engine sees, so a missed bubble means a missed word. Conversely, isolating text regions gives the OCR engine smaller, cleaner inputs, which improves recognition accuracy compared to full-page OCR.

**Production default: PaddleOCR detection models (Apache-2.0)**

PaddleOCR's PP-OCRv5 detection pipeline is the recommended production detector. It uses a DBNet++ text detection model with good CJK support, runs efficiently on GPU via PaddlePaddle, and carries a permissive Apache-2.0 license. While not manga-specialized, it handles clean speech bubbles, narration boxes, and UI text well. Accuracy on heavily stylized manga pages (SFX overlaid on artwork, irregular bubble shapes, text over complex backgrounds) will be lower than a manga-trained detector — this is an accepted tradeoff for licensing freedom.

**Benchmark reference: comic-text-detector (GPL-3.0)**

comic-text-detector (dmMaze) is the de facto standard for manga text detection, used by mokuro, BallonsTranslator, and manga-image-translator. It combines a UNet text segmentation model, DBNet line detector, and YOLOv5 block detector trained on ~13,000 anime/comic images. It outputs bounding boxes, text line polygons, and pixel-level segmentation masks. **This is not a shipped dependency** — it is used during development for benchmarking and accuracy comparison against the PaddleOCR detector, and as a reference for architecture decisions. Users who accept GPL can install it separately as an optional plugin.

**Long-term option: custom permissive manga detector**

If PaddleOCR detection proves insufficient for manga-specific layouts, a custom detector can be fine-tuned on manga data using a permissively licensed base (e.g., YOLOv8/v9 under AGPL-3.0 with an enterprise license, RT-DETR under Apache-2.0, or PaddleDetection). Training data can be sourced from the Manga109-s dataset (academic use) or synthetic generation. This is a Phase 2+ effort, deferred until real accuracy gaps are measured.

**Plugin interface:**

The detector is abstracted behind a `RegionDetector` interface, making it straightforward to swap implementations:

```python
class RegionDetector(Protocol):
    def detect(self, page_image: np.ndarray) -> list[DetectedRegion]:
        """Returns bounding boxes and optional masks for text regions."""
        ...

@dataclass
class DetectedRegion:
    bbox: tuple[int, int, int, int]  # (x1, y1, x2, y2)
    confidence: float
    mask: np.ndarray | None = None   # pixel-level segmentation if available
    region_type: str = "text"        # text | sfx | caption (if detector distinguishes)
```

### 4.2 Panel Detection & Reading Order

For vocabulary mining, strict reading order is optional — extracted text can be treated as a bag of words for tokenization. Reading order becomes important only for sentence-level context on cards.

**Simple approach (sufficient for word mining):** Process all detected text regions on a page without ordering. Tokenizer handles each region independently.

**Advanced approach (for sentence cards):** Use the Magi model ("The Manga Whisperer," CVPR 2024) for simultaneous panel detection, text box detection, and reading order prediction using a DAG-based algorithm. For simpler layouts, the recursive binary splitting algorithm from `manga109/panel-order-estimator` works on standard grid layouts.

**Reading direction convention:** Right-to-left for panels, top-right-to-bottom-left for bubbles within panels (standard Japanese manga).

### 4.3 Double-Page Spread Detection

Detect spreads via aspect ratio: any image with width/height > 1.3 is likely a double-page spread. Split at the midpoint and return the right page before the left page (Japanese reading order).

---

## 5. File Format Handling

### 5.1 Input Formats

| Format | Library | Strategy |
|--------|---------|----------|
| **PNG/JPG images** | Pillow / OpenCV | Direct input. Detect spreads via aspect ratio. |
| **PDF** | PyMuPDF (`fitz`) | **Try `page.get_text()` first** — if it returns usable Japanese text, skip OCR for that page. Fall back to `page.get_pixmap(dpi=300)` for image extraction + OCR. |
| **CBZ** | `zipfile` + `natsort` | Standard library. Natural sort filenames for correct page order. |
| **CBR** | `rarfile` | Requires external `unrar` binary. Natural sort for page order. |
| **EPUB** | `ebooklib` + BeautifulSoup | Parse spine for page order, extract embedded images. Some EPUB manga may have embedded text — check before OCR. |
| **Video (soft subs)** | `pysubs2` + `ffprobe` | Extract subtitle tracks directly. Skip OCR. |
| **Video (hard subs)** | DXcam / mss capture | Define subtitle region, capture frames, OCR. |

### 5.2 Page Extraction Pipeline

```
Input file
  → Format detection (by extension + magic bytes)
  → Format-specific handler:
      PDF:  try text extraction → fall back to image extraction at 300 DPI
      CBZ:  unzip → natural sort filenames
      CBR:  unrar → natural sort filenames
      EPUB: parse spine → extract images from HTML
      Images: direct pass-through
  → Spread detection (aspect ratio > 1.3)
  → If spread: split at midpoint, right page first
  → Output: ordered list of page images
```

---

## 6. Tokenization, Deconjugation & Normalization

### 6.1 Primary Tokenizer: SudachiPy

SudachiPy is the recommended tokenizer because its API is purpose-built for the dictionary-lookup use case:

- **`dictionary_form()`** — returns the uninflected lemma (食べた → 食べる). This is the dedup key and dictionary lookup key.
- **`normalized_form()`** — normalizes orthographic variants beyond inflection (附属 → 付属, シュミレーション → シミュレーション).
- **`reading_form()`** — returns katakana reading (for furigana on cards).
- **`part_of_speech()`** — POS tags for filtering particles, punctuation, etc.
- **`is_oov()`** — flags out-of-vocabulary tokens. Critical quality gate (see §6.4).

**Tokenization mode:** Use **Mode C** (compound word segmentation) for vocabulary cards. Mode A (shortest) over-segments compounds; Mode C keeps natural vocabulary units together.

```python
from sudachipy import Dictionary
tokenizer = Dictionary().create()
morphemes = tokenizer.tokenize("昨日は友達と食べに行った")
for m in morphemes:
    print(m.surface(), m.dictionary_form(), m.reading_form(), m.part_of_speech())
```

### 6.2 Alternative: fugashi + UniDic

MeCab (via the `fugashi` Cython wrapper) with UniDic offers the fastest tokenization and richest annotations (pitch accent, etymological category). Pair with NEologd for maximum coverage of modern slang and proper nouns. Better for edge cases in very colloquial text, but requires more manual compilation effort on Windows.

### 6.3 Deconjugation Strategy (Three-Tier)

**Tier 1 — Tokenizer lemmatization (handles ~95% of cases):**
Both SudachiPy and MeCab perform simultaneous segmentation and lemmatization via the Viterbi algorithm. Standard conjugations are resolved automatically.

**Tier 2 — Yomitan-style rule-based deinflection (fallback for colloquial forms):**
Port Yomitan's deinflection engine (JSON suffix replacement rules with POS constraints, recursive chaining). This handles contracted forms common in manga dialogue:

| Contracted Form | Full Form | Tokenizer Handles? | Deinflector Needed? |
|----------------|-----------|-------------------|---------------------|
| ～てる | ～ている | Usually yes | Sometimes |
| ～ちゃう | ～てしまう | Usually | Sometimes |
| ～なきゃ | ～なければ | Often | Sometimes |
| ～っす | ～です | Sometimes | Yes |
| ～とく | ～ておく | Rarely | Yes |
| ～てく | ～ていく | Rarely | Yes |

**Tier 3 — User review for unresolvable forms:**
Flag tokens that fail both tiers for manual review. This includes creative manga coinages, heavily dialectal speech, and OCR errors that produce non-words.

### 6.4 Furigana Handling

Furigana (small ruby text above/beside kanji) is a significant source of noise in manga OCR. Common problems include furigana characters merging with the main word during recognition, furigana being extracted as separate junk tokens, and furigana causing the OCR engine to produce doubled or garbled output. manga-ocr handles furigana better than most engines because it was trained on manga with furigana present, but post-OCR cleanup is still needed.

Mitigation strategies:
- **At the detection level:** If the detector provides segmentation masks, furigana regions can sometimes be identified by their small bounding box height relative to neighboring text. Consider filtering very small text regions before OCR.
- **At the tokenization level:** SudachiPy will typically split garbled furigana-merged text into OOV tokens, which the `is_oov()` gate catches. Single-hiragana tokens adjacent to kanji tokens are likely stray furigana and can be flagged.
- **At the card level:** When building cards, generate furigana from SudachiPy's `reading_form()` rather than trusting OCR-extracted ruby text. This is more reliable.

### 6.5 Sound Effect (SFX) Filtering

Manga pages are dense with onomatopoeia and sound effects (ドドドド, バキッ, ゴゴゴ, シーン) that may not be useful vocabulary for most learners. Without explicit filtering, SFX can dominate the candidate word list.

Detection heuristics:
- **POS-based:** SudachiPy tags onomatopoeia with POS category `感動詞` (interjection) or `副詞` (adverb) with subcategories that indicate mimetic/onomatopoeic words. Filter or flag these.
- **Pattern-based:** Repeated katakana characters (ドドド, ゴゴゴ), single katakana with っ (バキッ, ガシッ), and strings that are pure katakana of 2–4 characters with no JMdict match are likely SFX.
- **Region-based:** If the detector distinguishes region types (text vs SFX), SFX regions can be filtered before OCR. comic-text-detector provides this capability; PaddleOCR does not, so SFX filtering falls to the post-OCR stage.
- **User-configurable:** Some learners do want onomatopoeia cards. Make SFX filtering a toggle in config (`[filter] exclude_sfx = true`), defaulting to exclude.

### 6.6 Quality Filtering Pipeline

```
Raw OCR text
  → Unicode NFKC normalization
  → SudachiPy tokenization (Mode C)
  → Filter: remove particles, punctuation, symbols
  → Filter: remove likely SFX (see §6.5 heuristics)
  → Filter: remove likely stray furigana (single-hiragana adjacent to kanji)
  → For each remaining content word:
      → If is_oov(): flag as "needs review" (likely OCR noise or rare word)
      → Get dictionary_form() as dedup/lookup key
      → If dictionary_form() not found in JMdict: try Tier 2 deinflection
      → If still not found: try normalized_form()
      → If still not found: add to "unknown words" review queue
  → Output: list of (surface, lemma, reading, POS, confidence_tier)
```

### 6.7 Orthographic Variant Normalization

For improved dedup quality across volumes where the same word may be rendered differently (サーバー vs サーバ, 引っ越し vs 引越し), consider integrating **yurenizer**, which normalizes Japanese notation variations using the Sudachi Synonym Dictionary. This is optional but reduces false-negative dedup misses.

---

## 7. Dictionary Lookup & Sense Ranking

### 7.1 Primary Dictionary: jamdict (JMdict)

**jamdict** loads the ~200,000-entry JMdict database into SQLite for fast lookup. Install: `pip install jamdict jamdict-data`. Enable `memory_mode=True` for maximum speed.

```python
from jamdict import Jamdict
jam = Jamdict(memory_mode=True)
result = jam.lookup('食べる')
# result.entries → list of JMdict entries with glosses, POS, usage tags
# result.chars → KanjiDic2 character info
# result.names → JMnedict proper name entries
```

**Lookup cascade:** `dictionary_form` → `normalized_form` → surface form → deinflection candidates → JMnedict (for proper nouns).

### 7.2 Yomichan/Yomitan Dictionary Format Support

Supporting Yomichan/Yomitan dictionary ZIP imports gives access to the entire community dictionary ecosystem — J-E, J-J, frequency lists, pitch accent dictionaries, and specialty dictionaries. DokiDoki Dictionary uses this approach (ships JMdict built-in, supports Yomichan-format imports). This is a high-value feature for power users.

### 7.3 JLPT Tagging

JMdict does **not** include JLPT level data. Source JLPT tags from **stephenmk/yomitan-jlpt-vocab**, which maps Jonathan Waller's N5–N1 lists to JMdict entry IDs. Build a lookup table: `{jmdict_entry_id: jlpt_level}` and annotate words after dictionary lookup.

### 7.4 AI as Optional Ranking Layer (Not Dictionary)

For polysemous words, an optional AI layer can reorder dictionary senses based on surrounding sentence context. The architectural principle: **AI ranks existing dictionary definitions; it never generates new ones.** Cards are always backed by JMdict data for reproducibility and accuracy.

DokiDoki Dictionary uses Google's Gemini API for this purpose. Your tool could offer the same pattern with any LLM API (Gemini, Claude, local models). Core dictionary lookups and MeCab/Sudachi-based furigana work fully offline; AI ranking is an opt-in enhancement.

### 7.5 Handling Unknown Words

Strategy for words not in JMdict:
1. **JMnedict** — 800k+ proper names (character names, place names, etc.)
2. **NEologd entries** — if using MeCab with NEologd, it recognizes modern slang and brand names
3. **Flag for user review** — unknown words go to a review queue rather than silently generating incomplete cards
4. **Remote fallback** — optional jisho.org scraping or LLM-generated definitions (clearly marked as unverified)

---

## 8. Real-Time Screen OCR Workflow (Workflow B)

### 8.1 Screen Capture on Windows

**Primary: DXcam (DXGI Desktop Duplication API)**
- ~240 FPS, ~4ms latency at 1080p
- Returns numpy arrays directly
- Built-in change detection (only returns new frames when content changes)
- Can capture DirectX 11/12 exclusive fullscreen

```python
import dxcam
camera = dxcam.create()
frame = camera.grab(region=(left, top, right, bottom))  # numpy ndarray or None if unchanged
```

**Alternative: Windows.Graphics.Capture (WGC)**
- Modern Windows API with system-level window picker
- Clean per-window capture
- May not work with exclusive fullscreen games
- Accessible from Python via `winrt` bindings

**Cross-platform fallback: mss**
- 30–60 FPS via GDI calls on Windows
- Pure Python, zero dependencies
- 30–40× faster than PIL/ImageGrab

**Recommendation:** Support both DXcam (default) and mss (fallback). Add WGC as a third option if per-window capture demand emerges. Nudge users toward borderless windowed mode for games when fullscreen capture is inconsistent.

### 8.2 Game Text: Text Hooking vs. OCR

For visual novels and some RPGs, **text hooking** intercepts text directly from the game engine, bypassing OCR entirely. This is faster and more accurate.

- **Textractor** — classic text hooker, injects DLL to intercept Win32 text API calls
- **LunaTranslator** — actively maintained successor with broader engine support (Unity, Ren'Py, Tyranoscript)

The ideal tool supports **both**: text hooking when the game engine is supported, OCR as universal fallback. Consider a detection mechanism: attempt text hook first, fall back to OCR if no compatible hook is found.

### 8.3 Overlay Architecture (PySide6)

```python
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QWidget

class Overlay(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowFlags(
            Qt.WindowStaysOnTopHint |
            Qt.FramelessWindowHint |
            Qt.Tool  # hides from taskbar
        )
        self.setAttribute(Qt.WA_TranslucentBackground)

# For system-wide click-through (Win32):
import win32gui, win32con
hwnd = int(overlay.winId())
style = win32gui.GetWindowLong(hwnd, win32con.GWL_EXSTYLE)
win32gui.SetWindowLong(hwnd, win32con.GWL_EXSTYLE,
    style | win32con.WS_EX_LAYERED | win32con.WS_EX_TRANSPARENT)
```

### 8.4 Threading Model

Target: **<200ms total latency** (capture → OCR → lookup → display).

```
Main Thread (PySide6 event loop)
  ├── UI rendering, overlay positioning, popup display
  └── Receives results via Qt signals from worker threads

Capture Thread
  ├── Continuous DXcam capture with change detection
  ├── Captures ~400×200px ROI around cursor (not full screen)
  └── Pushes changed frames to OCR queue

OCR Thread
  ├── Picks latest frame from queue (drops stale frames)
  ├── Runs manga-ocr / MeikiOCR inference
  ├── Caches results keyed by perceptual image hash
  └── Pushes recognized text to NLP queue

NLP/Dictionary Thread
  ├── Tokenizes recognized text (SudachiPy)
  ├── Looks up definitions (jamdict)
  ├── Formats popup content
  └── Signals main thread with results
```

### 8.5 Hotkey System

- **Hold-to-scan:** While held, continuously capture and OCR around cursor (pynput or RegisterHotKey via ctypes)
- **Press-to-add:** Single press adds currently displayed word to session buffer
- **Session export:** Button in session panel exports buffer to Anki deck

Use **pynput** for cross-platform global hotkey registration. For production stability, consider migrating to native `RegisterHotKey` (Win32) for the Windows build.

### 8.6 Session Buffer Panel

A docked or floating PySide6 panel showing:
- List of words added during the current session (surface, reading, primary definition)
- Remove button per word
- "Export to Anki" button that triggers the build pipeline
- Deck name / subdeck configuration fields

---

## 9. Anki Deck Generation & Deduplication

### 9.1 Dual Export: genanki (Batch) + AnkiConnect (Live)

**genanki** for batch `.apkg` generation — works without Anki installed, supports hierarchical deck names, custom note types, media embedding.

**AnkiConnect** for real-time operations — REST API on `localhost:8765` when Anki is running. Critical capabilities:
- `canAddNotes` — preflight duplicate check against user's entire collection
- `addNote` / `addNotes` — create cards directly
- `findNotes` — query existing cards for dedup

**Hybrid strategy:** Use genanki for Workflow A batch export; use AnkiConnect for Workflow B real-time card creation when Anki is running; fall back to genanki `.apkg` if Anki is not running.

### 9.2 Deck Hierarchy

Anki uses `::` as the deck tree separator. Map to user's organizational model:

```
Manga:   SeriesName::Vol01::Ch03
Games:   GameTitle::Route::Chapter
Video:   ShowName::Season01::Episode03
Custom:  UserLabel::SubLabel
```

Users configure deck name and up to two levels of subdeck via CLI flags or GUI fields.

### 9.3 Note Model (Targeted Sentence Cards)

```python
import genanki

model = genanki.Model(
    1607392319,
    'JapaneseVocab',
    fields=[
        {'name': 'Expression'},       # dictionary form (kanji)
        {'name': 'Reading'},           # furigana format: 漢字[かんじ]
        {'name': 'Meaning'},           # English definition(s)
        {'name': 'Sentence'},          # source sentence with target highlighted
        {'name': 'SentenceReading'},   # sentence with furigana
        {'name': 'PartOfSpeech'},      # noun, verb, い-adj, etc.
        {'name': 'JLPTLevel'},         # N5–N1 or blank
        {'name': 'Source'},            # manga name, game title, etc.
        {'name': 'Screenshot'},        # optional context image
        {'name': 'FrequencyRank'},     # from frequency dictionary if available
    ],
    templates=[{
        'name': 'Recognition',
        'qfmt': '<div class="expression">{{Expression}}</div>'
                '<div class="sentence">{{Sentence}}</div>',
        'afmt': '{{FrontSide}}<hr id="answer">'
                '<div class="reading">{{furigana:Reading}}</div>'
                '<div class="meaning">{{Meaning}}</div>'
                '<div class="meta">{{PartOfSpeech}} · {{JLPTLevel}}</div>'
                '<div class="source">{{Source}}</div>',
    }],
    css='.card { font-family: "Noto Sans JP", "Yu Gothic", sans-serif; '
        'font-size: 24px; text-align: center; }'
        '.expression { font-size: 48px; }'
        '.sentence { font-size: 18px; color: #666; margin-top: 10px; }'
        '.reading { font-size: 28px; }'
        '.meaning { font-size: 20px; margin-top: 8px; }'
        '.meta { font-size: 14px; color: #999; margin-top: 12px; }'
        '.source { font-size: 12px; color: #bbb; margin-top: 4px; }'
)
```

### 9.4 GUID Strategy for Stable Dedup

Override genanki's GUID to hash only identity fields (expression + reading), not all fields. This ensures the same word always maps to the same GUID regardless of which source it was first found in:

```python
class JapaneseNote(genanki.Note):
    @property
    def guid(self):
        return genanki.guid_for(self.fields[0], self.fields[1])  # expression + reading
```

### 9.5 Dedup Key: Why (expression, reading)

The dedup key determines when two occurrences are considered "the same word." Several options exist, each with tradeoffs:

- **Surface form only** — Too narrow. 食べた and 食べる would be separate cards for the same word.
- **Lemma (dictionary_form) only** — Usually sufficient, but can merge words that share kanji but have different readings and meanings (e.g., 明日 read as あした vs あす, or 下手 as へた vs したて). For most vocabulary, this works, but edge cases exist.
- **Lemma + reading** — The recommended key. Two words that share the same dictionary form AND the same reading are the same vocabulary item. This correctly separates 下手[へた] (clumsy) from 下手[したて] (lower part) while still merging 食べた and 食べている into one card for 食べる.
- **Lemma + source deck** — Would allow the same word in different manga, which is the user's stated desired behavior. This is handled at a different layer (Layer 1 dedup is per-source; cross-source duplicates are intentionally allowed).

The GUID strategy (§9.4) and Layer 1 tracking both use `(dictionary_form, reading)` as the canonical dedup key.

### 9.6 Three-Layer Deduplication

**Layer 1 — Source-level tracking (your existing POC approach):**
Per-source `seen_words.json` prevents the same word from appearing in multiple chapters within one manga series. Keyed on `(dictionary_form, reading)`.

**Layer 2 — Application-level SQLite database:**
A central vocabulary database tracks all words ever exported, with source provenance, export date, and JLPT level. Before generating any deck, check candidates against this database.

**Layer 3 — Anki collection check (when Anki is running):**
Use AnkiConnect's `canAddNotes` to check against the user's full Anki collection, catching words added by other tools or manual entry.

---

## 10. Batch Pipeline Detail (Workflow A)

### 10.1 Scan Stage

```
Input: file path or directory
  → Format handler (§5): extract ordered page images
  → For each page:
      → If PDF with embedded text: extract text directly, skip OCR
      → Else:
          → Spread detection: split if aspect ratio > 1.3
          → Text region detection: PaddleOCR detector (default) via RegionDetector interface
          → OCR per detected region: manga-ocr
          → Store per region:
              - raw OCR text
              - bounding box coordinates
              - page ID and region index
              - cropped region image (for card screenshots and re-OCR)
              - OCR confidence score
          → Generate debug overlay: page image with detected regions drawn
            as colored bounding boxes (saved to data/<source>/<run_id>/debug/)
  → Output: scan.json (list of recognized text regions with metadata)
```

The debug overlay images are optional (controlled by `[scan] save_debug_overlays = true` in config) but strongly recommended during development and when evaluating a new detector. They make it immediately visible which regions were found, which were missed, and where false positives occur — enabling rapid comparison when benchmarking PaddleOCR against comic-text-detector or other detectors.

### 10.2 Review Stage

```
Input: scan.json
  → For each OCR text region:
      → Tokenize (SudachiPy Mode C)
      → Filter particles, punctuation, symbols
      → Filter likely SFX (§6.5) and stray furigana (§6.4)
      → For each remaining content token:
          → Quality check: is_oov() → flag for review
          → Deconjugate: dictionary_form() → Tier 2 deinflection if needed
          → Dedup check: against source seen_words + global vocab DB
          → Dictionary lookup: jamdict cascade
          → If found: add to approved candidates with full annotation
          → If not found: add to review queue
  → Output: review.json (approved words + flagged words for manual review)
  → Update: seen_words.json for this source
```

### 10.3 Build Stage

```
Input: review.json + user approvals/rejections
  → For each approved word:
      → Enrich: JLPT level, frequency rank, example sentence (from source context)
      → Format: build note fields per card template
      → Optionally: attach cropped screenshot from original page
  → Generate deck:
      → genanki: create deck with configured hierarchy
      → Stable GUIDs from expression + reading
  → Output: deck.apkg under data/<source>/<run_id>/
```

---

## 11. GUI Design

### 11.1 Framework: PySide6

PySide6 (Qt 6 for Python) is the recommended GUI framework:
- **LGPL license** — free for commercial use without viral licensing
- Native transparent window support for overlays
- Cross-platform (Windows, macOS, Linux)
- Rich widget library for review panels, settings, etc.
- Good threading integration (signals/slots across threads)

### 11.2 Application Windows

**Main Window:**
- Source/file selector (drag-and-drop supported)
- Pipeline progress (scan → review → build with progress bars)
- Deck configuration (name, subdeck structure)
- OCR engine selection
- Settings panel

**Review Panel:**
- Table of candidate words with columns: surface, lemma, reading, definition, POS, JLPT, confidence
- Checkbox to approve/reject each word
- Bulk actions (approve all N3+, reject all OOV, etc.)
- Search/filter by POS, JLPT level, confidence tier

**Real-Time Overlay:**
- Transparent, always-on-top, click-through popup
- Shows near cursor: word, reading, top 2-3 definitions
- Visual indicator for "added to buffer" confirmation
- Configurable size, opacity, font

**Session Buffer Panel:**
- Floating or docked window showing session word list
- Inline editing of definitions
- Deck name configuration
- Export button

---

## 12. Licensing Strategy

### 12.1 Decision: Permissive Path

The project will be built exclusively on permissively licensed components for all shipped dependencies. The door to future monetization remains open, and all production code can be distributed under any license (MIT, Apache-2.0, proprietary, etc.) without copyleft obligations.

GPL-licensed tools (mokuro, comic-text-detector) are used strictly as:
- **Benchmark tools** — to measure accuracy of the permissive detector against the manga-specialized standard
- **Reference implementations** — to study architecture, data flow, and design decisions during development
- **Optional experimental backends** — users who accept GPL terms can install them locally as plugins during development, but they are never bundled or required

This means the project **never imports, wraps, calls, or distributes** GPL code at runtime in the shipped application. The plugin interface (§4.1) makes it possible for a user to bring their own GPL detector, but the responsibility for GPL compliance shifts to the user's local environment.

### 12.2 License Map of Shipped Dependencies

| Component | License | Status |
|-----------|---------|--------|
| manga-ocr | **Apache-2.0** | ✅ Shipped — primary OCR engine |
| PaddleOCR / PaddlePaddle | **Apache-2.0** | ✅ Shipped — production text detector |
| owocr | **MIT** | ✅ Shipped — OCR engine abstraction |
| MeikiOCR | **MIT** | ✅ Shipped — real-time game text OCR |
| SudachiPy | **Apache-2.0** | ✅ Shipped — tokenizer |
| sudachidict_core | **Apache-2.0** | ✅ Shipped — tokenizer dictionary |
| fugashi | **MIT** | ✅ Shipped — alternative tokenizer |
| jamdict | **MIT** | ✅ Shipped — dictionary lookup |
| jamdict-data | **MIT** (data: CC BY-SA 4.0) | ✅ Shipped — must attribute JMdict/EDRDG |
| genanki | **MIT** | ✅ Shipped — Anki deck generation |
| PySide6 | **LGPL** | ✅ Shipped — standard dynamic linking, no copyleft issue |
| DXcam | **MIT** | ✅ Shipped — screen capture |
| mss | **MIT** | ✅ Shipped — cross-platform capture fallback |
| pynput | **LGPL** | ✅ Shipped — standard usage, no copyleft issue |

### 12.3 Reference-Only (Not Shipped)

| Component | License | Usage |
|-----------|---------|-------|
| comic-text-detector | **GPL-3.0** | Benchmark detector accuracy; study architecture |
| mokuro | **GPL-3.0** | Study pipeline design; compare output quality |

### 12.4 Data Attribution Requirements

JMdict, JMnedict, and KanjiDic2 are licensed under CC BY-SA 4.0 by the Electronic Dictionary Research and Development Group (EDRDG). The application must include visible attribution in its About/Credits screen and documentation, per the license terms. The share-alike clause applies to the data files, not to the software that reads them — using jamdict to query JMdict does not make your application CC BY-SA.

---

## 13. Technology Stack Summary

### 13.1 Core Dependencies

```
# OCR & Detection
manga-ocr              # Primary OCR engine (Apache-2.0)
paddlepaddle-gpu       # PaddlePaddle framework for PaddleOCR (Apache-2.0)
paddleocr              # Text region detection + fallback OCR (Apache-2.0)
owocr                  # OCR engine abstraction layer (MIT)
onnxruntime-gpu        # ONNX acceleration for manga-ocr / MeikiOCR

# NLP & Dictionary
sudachipy              # Tokenization + deconjugation (Apache-2.0)
sudachidict_core       # Sudachi dictionary (Apache-2.0)
jamdict                # JMdict dictionary access (MIT)
jamdict-data           # Precompiled JMdict database

# Anki
genanki                # Batch .apkg generation (MIT)
# AnkiConnect accessed via HTTP (localhost:8765)

# GUI
PySide6                # Qt 6 GUI framework (LGPL)

# Screen Capture (Windows)
dxcam                  # DXGI Desktop Duplication (MIT)
mss                    # Cross-platform fallback

# Hotkeys
pynput                 # Global hotkey registration

# File Formats
PyMuPDF                # PDF handling
rarfile                # CBR extraction
ebooklib               # EPUB extraction
natsort                # Natural sort for page ordering
pysubs2                # Subtitle extraction from video

# Utilities
Pillow                 # Image processing
opencv-python-headless # Image preprocessing (if needed)
numpy                  # Array operations (used by DXcam, OCR)
```

### 13.2 Optional / Enhancement Dependencies

```
# Cloud OCR (opt-in)
# Google Lens via owocr (no API key needed)
# Google Cloud Vision (API key required)

# AI Sense Ranking (opt-in)
# Gemini API or Anthropic API for context-aware definition ranking

# Text Hooking (opt-in, for visual novels)
# Textractor / LunaTranslator integration via IPC

# Extended Normalization
# yurenizer — Sudachi Synonym Dictionary-based variant normalization
```

---

## 14. Data Model

### 14.1 SQLite Schema (Central Vocabulary Database)

```sql
CREATE TABLE vocabulary (
    id INTEGER PRIMARY KEY,
    expression TEXT NOT NULL,        -- dictionary form (kanji)
    reading TEXT NOT NULL,            -- katakana reading
    meanings TEXT,                    -- JSON array of English glosses
    part_of_speech TEXT,              -- noun, verb, i-adj, etc.
    jlpt_level TEXT,                  -- N5, N4, N3, N2, N1, or NULL
    frequency_rank INTEGER,           -- from frequency dictionary
    first_seen_source TEXT,           -- manga/game name
    first_seen_date TEXT,             -- ISO date
    export_count INTEGER DEFAULT 0,   -- how many decks this word has been in
    UNIQUE(expression, reading)
);

CREATE TABLE export_history (
    id INTEGER PRIMARY KEY,
    vocabulary_id INTEGER REFERENCES vocabulary(id),
    deck_name TEXT NOT NULL,          -- full deck::subdeck path
    export_date TEXT NOT NULL,
    source_context TEXT,              -- sentence where word was found
    screenshot_path TEXT              -- optional cropped image path
);

CREATE TABLE sessions (
    id INTEGER PRIMARY KEY,
    session_date TEXT NOT NULL,
    source_label TEXT,                -- what the user was reading/playing
    words_added INTEGER DEFAULT 0,
    deck_exported TEXT                -- deck name if exported, NULL if not
);
```

### 14.2 File Artifacts (Per Source/Run)

```
data/
  <source>/                          # e.g., "one-piece"
    known_words.txt                  # user-maintained exclusion list
    seen_words.json                  # all words seen across runs
    <run_id>/                        # e.g., "vol01-ch03"
      scan.json                      # OCR results with regions
      review.json                    # filtered/annotated candidates
      deck.apkg                      # generated Anki deck
      screenshots/                   # cropped text region images
      debug/                         # page images with detected regions drawn (optional)
```

### 14.3 Configuration (TOML)

```toml
[project]
name = "my-japanese-mining"
default_ocr_engine = "manga-ocr"
default_tokenizer = "sudachi"

[ocr]
engine = "manga-ocr"                 # manga-ocr | meikiocr | google-lens | paddleocr
onnx_acceleration = true
gpu_device = 0

[ocr.fallback]
enabled = true
engine = "google-lens"

[tokenizer]
engine = "sudachi"
mode = "C"                           # A (short) | B (middle) | C (long/compound)

[dictionary]
primary = "jamdict"
jlpt_data_path = "data/jlpt_tags.json"
ai_ranking = false
ai_provider = "gemini"               # gemini | claude | local

[anki]
default_deck_prefix = ""
note_type = "JapaneseVocab"
connect_port = 8765
prefer_ankiconnect = true            # use AnkiConnect when Anki is running

[capture]
engine = "dxcam"                     # dxcam | mss | wgc
roi_width = 400
roi_height = 200
change_detection = true

[hotkeys]
scan_hold = "ctrl+shift"
add_word = "ctrl+shift+a"
export_session = "ctrl+shift+e"

[filter]
exclude_particles = true
exclude_sfx = true                   # filter out likely sound effects / onomatopoeia
exclude_stray_furigana = true        # filter single-hiragana tokens adjacent to kanji
exclude_below_jlpt = ""             # e.g., "N4" to exclude N5/N4 words
min_confidence = "tier1"             # tier1 (tokenizer), tier2 (deinflector), tier3 (unknown)

[scan]
save_debug_overlays = true           # save page images with detected regions drawn
detector = "paddleocr"               # paddleocr (default) | custom plugin name
```

---

## 15. Cross-Platform Strategy

### 15.1 macOS

| Component | Windows | macOS Replacement |
|-----------|---------|-------------------|
| Screen capture | DXcam (DXGI) | mss or CGWindowListCreateImage via pyobjc |
| WinRT OCR | OneOCR | Apple Vision framework via pyobjc |
| Overlay | PySide6 + Win32 | PySide6 (native Qt transparency works) |
| Hotkeys | pynput / RegisterHotKey | pynput (cross-platform) |
| Text hooking | Textractor DLL injection | Not applicable (different game ecosystem) |

Everything else (manga-ocr, SudachiPy, jamdict, genanki, PySide6 core) works unchanged.

### 15.2 iOS (Future)

Python is not production-ready on iOS. The practical path:

1. **Shared Rust core** — OCR pipeline, tokenization (via lindera/sudachi.rs), dictionary lookup compiled via UniFFI for Swift interop
2. **CoreML** — Convert manga-ocr PyTorch model to CoreML for on-device inference
3. **Native SwiftUI** — UI layer
4. **Significant effort** — defer until desktop app is mature

---

## 16. Phased Development Plan

### Phase 1 — Core Pipeline Upgrade (Weeks 1–4)
**Goal:** Replace POC's weaker components with production-quality alternatives.

- [ ] Replace Tesseract with manga-ocr (or owocr abstraction)
- [ ] Switch tokenization from current normalizer to SudachiPy
- [ ] Integrate jamdict for dictionary lookup (replacing current dictionary.py)
- [ ] Add JLPT tagging via external word list
- [ ] Add `is_oov()` quality gating
- [ ] Implement Yomitan-style deinflection as Tier 2 fallback
- [ ] Migrate state from flat files to SQLite for vocabulary tracking
- [ ] Add TOML configuration

### Phase 2 — Batch Manga Parsing (Weeks 5–8)
**Goal:** Process full manga volumes without manual screenshotting.

- [ ] Implement file format handlers (PDF, CBZ, CBR, EPUB)
- [ ] Implement `RegionDetector` plugin interface
- [ ] Integrate PaddleOCR detection as the default `RegionDetector`
- [ ] Add spread detection and splitting
- [ ] PDF embedded text extraction (try text before OCR)
- [ ] Implement full scan stage on page images with region detection
- [ ] Add cropped region image saving for card screenshots
- [ ] Add debug overlay image generation (detected regions drawn on page)
- [ ] Implement furigana noise filtering (§6.4)
- [ ] Implement SFX filtering with configurable toggle (§6.5)
- [ ] Benchmark PaddleOCR detection accuracy against comic-text-detector (reference) on 5+ manga volumes
- [ ] Document accuracy gaps and determine if custom detector training is warranted

### Phase 3 — Real-Time Overlay (Weeks 9–14)
**Goal:** Working hover-dictionary with session buffer and Anki export.

- [ ] Implement DXcam screen capture with ROI and change detection
- [ ] Build PySide6 transparent overlay (popup near cursor)
- [ ] Implement threading model (capture → OCR → NLP → display)
- [ ] Add global hotkeys (hold-to-scan, press-to-add)
- [ ] Build session buffer panel
- [ ] Integrate AnkiConnect for live duplicate checking
- [ ] ONNX Runtime acceleration for <200ms latency target
- [ ] Test with manga reader apps, visual novels, windowed games

### Phase 4 — Polish & Integration (Weeks 15–18)
**Goal:** Production-quality UX and advanced features.

- [ ] Build PySide6 main window (source selector, pipeline progress, settings)
- [ ] Build review panel (approve/reject candidates, bulk actions)
- [ ] Add Yomichan-format dictionary import support
- [ ] Add soft subtitle extraction for video files
- [ ] Optional: AI sense ranking integration
- [ ] Optional: Textractor/LunaTranslator text hooking integration
- [ ] Installer/packaging for Windows distribution
- [ ] User documentation

### Phase 5 — macOS Port (Future)
- [ ] Replace DXcam with mss / CGWindowListCreateImage
- [ ] Test full pipeline on macOS
- [ ] Optional: Apple Vision framework as OCR alternative

---

## Appendix A: Key Reference Projects

| Project | What It Does | What to Learn From It |
|---------|-------------|----------------------|
| **mokuro** (GPL-3.0, reference only) | Full manga OCR → selectable text HTML | Pipeline architecture, detection + OCR integration patterns |
| **comic-text-detector** (GPL-3.0, benchmark only) | Manga text region detection | Detection accuracy baseline for benchmarking PaddleOCR |
| **DokiDoki Dictionary** | Real-time screen OCR hover dictionary | UX patterns, offline-first + AI ranking architecture, Anki export flow |
| **owocr** | Multi-engine OCR abstraction | Engine plugin pattern, clipboard/screen monitoring |
| **Yomitan** | Browser popup dictionary | Deinflection rules (JSON), dictionary format standard, AnkiConnect integration |
| **JL** | Desktop Japanese lookup tool | Yomichan-format dictionary consumption, recursive lookups |
| **Game2Text** | Hybrid text-hooking + OCR for games | Architecture for combining hooking and OCR |
| **Textractor / LunaTranslator** | Game text hooking | Text extraction from VN/game engines without OCR |
| **Magi (Manga Whisperer)** | CVPR 2024 manga understanding | Panel detection, reading order, character identification |
| **MeikiOCR** | High-speed game text OCR | ONNX pipeline for real-time game UI text |

## Appendix B: Useful Data Sources

| Resource | URL / Package | Use |
|----------|--------------|-----|
| JMdict (English) | `jamdict` + `jamdict-data` | Primary J-E dictionary |
| JMnedict | Included in jamdict | Proper name lookup |
| KanjiDic2 | Included in jamdict | Kanji character info |
| JLPT word lists | `stephenmk/yomitan-jlpt-vocab` | JLPT level tagging |
| Frequency lists | BCCWJ corpus / Innocent Corpus | Word frequency ranking |
| Yomichan dictionaries | Community ZIP packages | Extended dictionary ecosystem |
| Sudachi Synonym Dict | Via yurenizer | Orthographic normalization |
