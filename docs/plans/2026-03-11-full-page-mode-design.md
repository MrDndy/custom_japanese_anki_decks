# Full Manga Page Scan Mode Design

## Goal

Add a new scan mode that accepts full manga pages and extracts only:

- speech bubbles
- narration boxes

The design should preserve the current workflow that already works well for sentence-sized screenshots. Full-page support is an additive preprocessing step, not a replacement for the existing OCR/tokenization pipeline.

## Recommendation

Do not try to make the current full-image OCR parse an entire page as one text stream.

Instead, add a page-segmentation stage before OCR:

1. detect likely speech/narration regions on the page
2. crop each region
3. sort regions into approximate manga reading order
4. OCR each crop independently
5. pass each crop through the existing normalization and candidate extraction path
6. merge region results into the existing `scan.json` output

This matches how the current project already succeeds on smaller sentence screenshots.

## Scope

### In Scope

- full manga page input
- detection of speech bubbles and narration boxes
- per-region OCR and candidate extraction
- merged page-level candidates
- artifact metadata for debugging
- graceful fallback when segmentation is weak

### Out of Scope

- game UI text
- reader overlays or watermarks
- sound effects
- perfect sentence reconstruction across an entire page
- changes to `review` or `build` semantics

## Why The Current Full-Page Input Fails

The current `scan` stage assumes one image is one reasonably tight OCR target.

On a full manga page, failure happens before useful tokenization:

- OCR sees multiple disconnected text regions at once
- reading order across bubbles is ambiguous
- narration, speech, decorative text, and noise are mixed together
- candidate extraction then works from a polluted text stream

The main missing capability is page layout analysis, not a small improvement to tokenization.

## Proposed User Experience

Add a new page-aware option to `scan` and `run`.

Example:

```powershell
.\.venv312\Scripts\python -m jp_anki_builder.cli run `
  --images "C:\path\to\pages" `
  --source "Miharu" `
  --run-id "Vol01-Ch00" `
  --data-dir data `
  --ocr-mode manga-ocr `
  --page-mode segmented `
  --online-dict off `
  --volume 01 `
  --chapter 00
```

### CLI Shape

Recommended option:

- `--page-mode off|segmented`

Behavior:

- `off`: current behavior, treat each image as one OCR target
- `segmented`: detect subregions on each page and OCR those instead

Do not overload `ocr-mode` with page-layout behavior. OCR backend selection and page segmentation are different concerns.

## Architecture

### Current Flow

`image -> OCR -> normalize/tokenize -> candidates -> scan artifact`

### New Full-Page Flow

`page image -> region detector -> ordered crops -> OCR per crop -> normalize/tokenize per crop -> merged candidates -> scan artifact`

### Module Responsibilities

Recommended new module:

- `src/jp_anki_builder/page_segments.py`

Responsibilities:

- detect candidate text regions
- classify likely region type (`speech`, `narration`, `unknown`)
- sort regions into reading order
- crop regions for OCR
- expose region confidence/quality metadata

Keep these existing modules mostly unchanged:

- `ocr.py`: OCR providers remain region-level text extractors
- `normalization.py`: still normalize OCR text from one region at a time
- `review.py`: unchanged, consumes merged candidate list
- `build.py`: unchanged except for consuming the same review output as today

## Detection Strategy

Use a two-phase detector.

### Phase 1: Candidate Region Proposal

Start with pragmatic image heuristics rather than a heavy ML dependency.

Possible approach:

1. convert page to grayscale
2. apply thresholding / adaptive thresholding
3. find connected components or contours
4. merge nearby text-like components into larger candidate boxes
5. expand boxes slightly to avoid clipping characters

The detector is not trying to identify every sentence precisely. It is trying to produce OCRable crops that isolate one speech bubble or narration box at a time.

### Phase 2: Region Filtering

Discard weak candidates using simple heuristics:

- too small
- too large relative to page
- extreme aspect ratios unlikely to contain bubble/narration text
- almost no dark/light contrast
- OCR returns little or no Japanese text

Region classification can be heuristic at first:

- narration boxes often have rectangular boundaries and tighter text blocks
- speech bubbles often have irregular rounded boundaries and looser interior space

Do not block OCR on classifier uncertainty. A useful `unknown` region is better than dropping text prematurely.

## Reading Order

Reading order is approximate and should be explicit in the artifact.

Recommended initial heuristic for Japanese manga:

1. group regions by vertical overlap bands
2. within each band, sort from right to left
3. sort bands from top to bottom

This will not be perfect for every layout, so the system should record ordering confidence.

### Important Rule

Ordering is for artifact readability and possible future sentence grouping.

It must not be treated as guaranteed sentence structure.

The current downstream pipeline only needs per-region OCR text and merged candidates. That is a strength; keep it.

## OCR Integration

Once a page has been segmented:

1. crop each region
2. pass each crop to the selected OCR backend
3. collect `text` plus `alternate_texts` exactly as today where supported
4. normalize/tokenize each region independently

This reuses the current OCR and normalization code instead of inventing a new page-level OCR path.

## Artifact Design

Keep `scan.json` as the main artifact, but extend page records with region data.

### Existing Top-Level Fields To Preserve

- `source`
- `run_id`
- `ocr_mode`
- `ocr_language`
- `normalization_method`
- `online_dict`
- `image_count`
- `records`
- `candidates`

### Proposed Page Record Shape

Each page record should continue to represent one original input image.

Recommended fields:

```json
{
  "image": "path/to/page.png",
  "page_mode": "segmented",
  "page_confidence": 0.78,
  "ordering_confidence": 0.62,
  "text": "optional combined preview text",
  "alternate_texts": [],
  "surface_tokens": [],
  "normalized_candidates": [],
  "candidates": ["冒険", "勇者"],
  "regions": [
    {
      "index": 1,
      "bbox": {"x": 100, "y": 120, "w": 240, "h": 180},
      "kind": "speech",
      "detector_confidence": 0.81,
      "ordering_rank": 1,
      "ordering_confidence": 0.62,
      "text": "冒険に行く",
      "alternate_texts": ["冒険へ行く"],
      "surface_tokens": ["冒険", "に", "行く"],
      "normalized_candidates": [],
      "candidates": ["冒険", "行く"]
    }
  ]
}
```

### Notes

- Keep page-level `candidates` as the deduped union of all region candidates for compatibility.
- Region-level `normalized_candidates` should follow the same schema already used today.
- Page-level `text` can be a debug preview created by concatenating ordered region texts, but it should not be treated as authoritative sentence flow.

## Failure Behavior

Full-page mode must fail conservatively.

### Case 1: No Usable Regions Found

Behavior:

- save a `scan.json` record noting segmentation failure
- emit a warning that the page could not be segmented reliably
- suggest using smaller screenshots

### Case 2: Low-Confidence Regions Only

Behavior:

- continue
- save the low-confidence regions and confidence metadata
- avoid claiming accurate ordering or sentence reconstruction

### Case 3: OCR Succeeds But Region Quality Is Poor

Behavior:

- allow review/build to continue from extracted candidates
- retain enough metadata in `scan.json` for later debugging

### Core Principle

Never invent confidence the system does not have.

## Resume Support

Current scan already supports incremental write and `--resume`.

Full-page mode should preserve that behavior:

- one page image still maps to one page record
- partially processed runs should skip completed pages, not completed regions
- region metadata is written within the page record as part of the page result

This keeps the resume model simple.

## Testing Strategy

### Unit Tests

Add tests for:

- region sorting heuristic
- candidate region filtering
- page-level artifact schema with `regions`
- fallback behavior when no regions are found

### Integration Tests

Add fixture-driven tests for:

- one page with two speech regions
- page with speech plus narration
- page with no valid regions
- resume behavior in segmented page mode

### Non-Goals For Automated Tests

Do not try to prove perfect manga reading order from synthetic tests.

Instead, test:

- deterministic ordering behavior
- stable artifact shape
- correct reuse of existing OCR/normalization pipeline

## Recommended Implementation Plan

### Phase 1: Feature Skeleton

1. add CLI flag `--page-mode off|segmented`
2. thread the option through `Pipeline.scan()` and `run_scan()`
3. add new page segmentation module with placeholder heuristic detector
4. extend `scan.json` schema to support region data

### Phase 2: Heuristic Segmentation

1. implement contour/component-based region proposal
2. add region filtering heuristics
3. implement reading-order sorting
4. crop and OCR each region

### Phase 3: Validation And Tuning

1. test on real manga pages
2. tune thresholds for region merging/filtering
3. improve debug output and scan warnings
4. document when users should still prefer sentence screenshots

## Practical Recommendation For Users

Even after this feature is added, sentence-sized screenshots should remain the recommended path for highest accuracy.

Full-page mode should be presented as:

- more convenient
- less precise
- best-effort

That is the honest product position for the foreseeable future.

## Handoff Notes For Another AI Session

If implementing this in a later session:

1. do not rewrite `review` or `build`
2. preserve current sentence-screenshot behavior as default
3. treat page segmentation as a preprocessing layer inside `scan`
4. keep `scan.json` backward-compatible at the top level
5. prioritize debuggability over ambitious sentence reconstruction

The shortest correct path is:

- add `--page-mode segmented`
- detect ordered crops
- OCR each crop with existing providers
- emit region metadata and merged candidates

Avoid trying to solve full-page sentence reconstruction end to end in one step.
