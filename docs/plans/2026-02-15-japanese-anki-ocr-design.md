# Japanese OCR to Anki Deck Builder - Design

Date: 2026-02-15
Status: Approved

## Goals
- Capture Japanese text from screenshots as the first MVP input method.
- Convert extracted words into organized Anki decks with hierarchical deck names.
- Generate two-way flashcards:
  - Front: Kanji + Reading, Back: English meanings
  - Front: English meanings, Back: Kanji + Reading
- Exclude particles and known words.
- Prevent duplicate words within a single source across chapters/volumes.

## Non-Goals (MVP)
- GUI (CLI first, GUI later using the same pipeline modules).
- Audio generation (deferred to v2).
- Cross-source deduplication (only dedup inside a source in MVP).

## Tooling Decision
Use Python for MVP.

Rationale:
- Best fit for OCR/NLP/dictionary ecosystem.
- Fast iteration speed and maintainability for this workflow.
- Easiest for the user to read/debug/extend.

## Architecture
Modular Python CLI with these components:

- capture
  - Accept one image file or a folder of screenshots.
  - Normalize image formats and order.

- ocr
  - Extract Japanese text from images.
  - Persist raw OCR text with source image metadata.

- tokenize
  - Segment OCR text into candidate words.
  - Deduplicate and score candidates with simple confidence/frequency heuristics.

- filtering
  - Remove particles/function words by default.
  - Exclude words from a user-managed known words list.
  - Flag/exclude words already seen in the same source vocabulary index.

- review
  - Interactive CLI review to keep/remove candidates.
  - Allow remove + save-to-known-list action.

- enrich
  - Dictionary enrichment for reading and meanings.
  - Offline-first lookup, online fallback.
  - Keep top 2-3 meanings for card content.

- deck_builder
  - Build Anki note model and export .apkg.
  - Create hierarchical deck names like Source::VolumeXX::ChapterYY.

- storage
  - Persist intermediate artifacts to support reruns/resume and traceability.

- cli
  - Orchestrates full and stage-based commands.

## CLI Commands (MVP)
- scan
  - Input images + source metadata.
  - Output OCR and token candidate artifacts.

- review
  - Apply filters first (particles, known words, source dedup).
  - Interactive keep/remove and optional save-to-known-list.

- build
  - Enrich approved words.
  - Generate both card directions.
  - Export .apkg.

- run
  - Convenience command for scan -> review -> build.

## Data and Persistence
- known words list
  - User-managed file, e.g. data/known_words.txt.
  - Used each run to auto-exclude known vocabulary.

- source vocabulary index
  - Per-source store, e.g. data/sources/<source_id>/seen_words.json.
  - Tracks canonical approved words already used in that source.
  - Prevents duplicate cards across chapters/volumes within that source.

- run artifacts
  - Persist OCR output, token candidates, review decisions, and enrichment results.
  - Enables recovery/resume without repeating OCR.

## Filtering and Dedup Rules
- Built-in particle/function-word exclusion enabled by default.
- Known words exclusion enabled by default.
- Source-level dedup exclusion enabled by default.
- Duplicates can be optionally re-included during review for edge cases.
- Source vocabulary index updates only after final approval/build to avoid storing OCR noise.

## Deck and Card Design
- Deck hierarchy:
  - Source::VolumeXX::ChapterYY (omit missing levels cleanly).

- Card directions (both generated automatically):
  - Direction A: Kanji + Reading -> English meanings
  - Direction B: English meanings -> Kanji + Reading

## Error Handling and Resilience
- Validate missing/invalid image paths early.
- Surface OCR failures per image and continue batch where possible.
- Record unresolved dictionary lookups for review.
- Support rerun from persisted artifacts rather than restarting full pipeline.

## Testing Strategy (Design-Level)
- Unit tests:
  - Token filtering rules (particles, known words, dedup).
  - Deck naming and card field mapping.
  - Dictionary fallback order and top-meaning truncation.

- Integration tests:
  - End-to-end sample: screenshots -> OCR artifacts -> reviewed words -> .apkg output.
  - Source dedup behavior across multiple chapter runs.

- Manual verification:
  - Import generated .apkg into Anki and inspect both card directions and deck hierarchy.

## Future Extensions
- GUI over the same core modules.
- Optional TTS audio attachment.
- Cross-source dedup policy.
- Clipboard/hotkey capture and live snip capture.

## Acceptance Criteria (MVP)
- User can point CLI at screenshot files/folders.
- OCR text is tokenized into candidate words.
- Particle and known-word filtering works.
- Review step supports keep/remove and save-to-known-list.
- Dictionary enrichment provides reading and meanings (offline first, online fallback).
- .apkg is generated with both card directions.
- Decks are hierarchical by source/volume/chapter.
- Duplicate words are not recreated across chapters within the same source.
