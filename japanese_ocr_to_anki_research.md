# Building a Japanese OCR-to-Anki Pipeline for Manga, Games, and Subtitles

## What you’re actually trying to solve

Your application has two hard problems that interact:

1. **Text acquisition**: getting Japanese text out of places where the user can’t copy/paste (rendered game text, manga panels in an image viewer, “burned-in” subtitles, etc.). This often implies *screen/window capture + OCR*, unless the underlying software exposes text in a machine-readable way (for example, a subtitle stream track, or text rendering calls you can hook).

2. **Normalization for lookup**: once you have text, you want to reliably map what the user sees (often inflected/conjugated) to a **dictionary form** (lemma) so you can look it up in a dictionary dataset and generate consistent Anki notes. Modern Japanese morphological analyzers expose dictionary-form and reading-form fields directly, but OCR noise and partial word captures mean you often also want a **rule-based deinflector** as a fallback.

A practical “definition of done” for your product usually looks like:

- Works on **horizontal and vertical** Japanese text.
- Handles **furigana** and stylized fonts.
- Supports **low-latency** capture for games/video.
- Produces dictionary-ready tokens: surface form, dictionary form, and reading.

## Ways to acquire text that you can’t copy/paste

The best method depends on the source. A key finding is that **OCR is not always the best first step**—when you can avoid OCR, you avoid an entire class of recognition errors.

### Direct extraction

#### Game / VN text hooking
Tools like **Textractor** hook text output functions before text is rasterized, which can be much cleaner than OCR.

**Pros**
- Very accurate when supported
- Preserves line breaks
- Avoids font and aliasing artifacts

**Cons**
- Platform / engine dependent
- GPL-3.0 licensing for Textractor
- May be less reliable on newer games

#### Subtitle stream extraction
For videos, check whether subtitles are **text-based streams** (SRT, ASS/SSA) before doing OCR.

**Use OCR only when**
- subtitles are burned into the frame
- subtitles are image-based rather than text-based

### Accessibility / UI APIs
Some desktop apps expose text via accessibility APIs, but games often do not. This is sometimes viable for standard UI apps, but usually not the main path for games.

### Screen/window capture + OCR
The universal fallback is:

1. capture display/window/region  
2. detect likely text region  
3. OCR the region  
4. post-process and normalize  

#### Capture APIs by platform

**Windows**
- **Desktop Duplication API (DXGI)**: efficient frame capture with dirty rects / move rects
- **Windows.Graphics.Capture**: modern secure capture of windows/displays

**macOS**
- **ScreenCaptureKit**: high-performance modern capture API

**Linux / Wayland**
- **PipeWire + xdg-desktop-portal**: common modern path

## OCR engines worth considering

### OS-provided OCR

#### Windows OCR
**Windows.Media.Ocr** is local and fast for Windows-only tools.

**Strengths**
- Offline
- Structured word/line output
- Works well with “select region then OCR” UX

**Limitations**
- Requires installed language packs
- Windows packaging constraints apply

#### Apple Vision
**VNRecognizeTextRequest** is the native Apple option, but vertical Japanese should be validated carefully in practice.

### Open-source OCR

#### Tesseract
Use **jpn** and **jpn_vert** models.

**Why it matters**
- Explicit vertical Japanese model
- Flexible deployment
- Offline and open source

**Tradeoff**
- Accuracy may lag specialized models on stylized manga or noisy game text

#### Manga OCR
**manga-ocr** is the most purpose-built option for manga-like Japanese text.

**Strengths**
- Designed for manga
- Handles vertical/horizontal layouts
- Better with furigana and stylized text
- Good fit for digital manga workflows

#### PaddleOCR / EasyOCR
Useful general multilingual OCR stacks, especially if you want broader OCR framework support and local inference.

### Cloud OCR

#### Google Cloud Vision
Strong OCR with language support and language hints.

#### Azure Read / Document Intelligence OCR
Strong multilingual OCR, including Japanese support.

#### Amazon Textract
Generally **not a fit** for Japanese manga/game OCR because official docs do not position it well for this use case and vertical Japanese is a problem.

### Real-time OCR design points

To make OCR feel real-time, architecture matters more than tiny model differences:

- capture only changed areas
- OCR only stable regions like dialogue boxes or subtitle bands
- use smaller, cleaner crops
- handle protected video content gracefully

## Reverse conjugation and dictionary form recovery

This is best treated as a two-layer system:

1. **Morphological analysis / lemmatization**
2. **Rule-based deinflection fallback**

### Morphological analyzers

#### Sudachi / SudachiPy
Strong fit for your use case because it exposes:

- `dictionary_form()`
- `normalized_form()`
- `reading_form()`

This makes it easy to convert recognized text into Anki-friendly structured fields.

#### MeCab + UniDic via fugashi
Also strong, especially when you want:

- lemma
- reading
- base orthography
- robust tokenization

### Rule-based deinflection
Use this as a fallback when:

- OCR introduces errors
- user selection is partial
- tokenization fails cleanly
- stylized or slang forms break analyzer assumptions

**Best model to study**
- **Yomitan / Yomichan deinflection approach**

This style of system:
- applies suffix-based rewrite rules
- tracks grammatical conditions
- chains multiple transforms
- tests candidates against dictionary entries

## Recommended normalization strategy

A practical approach:

1. Run a morphological analyzer over the OCR line
2. Extract tokens with:
   - surface form
   - dictionary form
   - reading
   - POS if available
3. If lookup fails or tokenization is messy, run rule-based deinflection
4. Try candidate lemmas against your dictionary index
5. Store both original seen form and normalized form

## Reference architecture for your application

### Capture layer
Choose by platform:

- **Windows**: Desktop Duplication API or Windows.Graphics.Capture
- **macOS**: ScreenCaptureKit
- **Linux**: PipeWire + portal-based capture

### OCR layer
Choose by content:

- **Digital manga / comic panels**: manga-ocr
- **General desktop OCR**: Tesseract or Windows OCR
- **Cloud fallback**: Google Vision or Azure Read

### Region selection
Possible strategies:

- manual ROI selection
- remembered template ROI per game/window
- automatic dialogue/text region detection

### Text normalization layer
Post-process OCR output:

- normalize whitespace and line breaks
- normalize punctuation variants
- optionally separate or strip furigana
- tokenize and lemmatize

### Lemmatization layer
Preferred stack:

- **Primary**: SudachiPy or MeCab+UniDic
- **Fallback**: Yomitan-style deinflection rules

### Dictionary lookup layer
After normalization, query local dictionary data using lemma candidates.

### Anki integration
Use **AnkiConnect** for local note creation.

Suggested card fields:

- `expression_surface`
- `expression_lemma`
- `reading`
- `definition`
- `example_sentence`
- `source_title`
- `source_context`
- `screenshot_path`
- `tags`

## Recommended toolchains by scenario

### Scenario: PC games / VNs
**Best first choice**
- text hooking when possible

**Fallback**
- ROI capture + OCR

**Suggested stack**
- Textractor when compatible
- Windows capture API
- SudachiPy
- AnkiConnect

### Scenario: digital manga
**Best first choice**
- manga-ocr

**Enhancement**
- speech bubble or text-region detection before OCR

**Suggested stack**
- image crop / panel region
- manga-ocr
- SudachiPy or MeCab+UniDic
- AnkiConnect

### Scenario: video subtitles
**Best first choice**
- extract subtitle stream directly if text-based

**Fallback**
- OCR subtitle band only

**Suggested stack**
- subtitle parser if track exists
- otherwise region capture
- OCR
- lemma pipeline
- AnkiConnect

## Practical implementation recommendation

If you want the highest-value starting point:

1. Build the pipeline around **region capture + OCR + SudachiPy + AnkiConnect**
2. Use **manga-ocr** for manga/images
3. Use **Windows capture APIs** for live app/game text on Windows
4. Add **Yomitan-style deinflection fallback** after the initial lemma pipeline works
5. Add direct extraction later:
   - game text hooking
   - subtitle stream parsing

## Security, privacy, and licensing concerns

### Security / capture constraints
- protected content may not be capturable
- some OS capture APIs show system indicators or require secure picker flows

### Privacy
- local OCR is better for privacy and offline workflows
- cloud OCR adds latency, cost, and data handling concerns

### Licensing
- **Textractor**: GPL-3.0
- **Tesseract / tessdata**: permissive/open source
- **manga-ocr**: permissive/open source
- dictionary datasets may have redistribution constraints

## Final recommendation

For a real, shippable MVP, the strongest starting architecture is:

- **Capture**
  - Windows: Windows.Graphics.Capture or Desktop Duplication
- **OCR**
  - manga: **manga-ocr**
  - general fallback: **Tesseract jpn + jpn_vert** or Windows OCR
- **Normalization**
  - **SudachiPy** or **MeCab + UniDic**
- **Fallback deinflection**
  - **Yomitan-style rule engine**
- **Card creation**
  - **AnkiConnect**

That gives you a pipeline that is:
- realistic to prototype
- good for personal Japanese study workflows
- extensible across manga, games, and subtitles
- structured enough for automatic Anki note generation
