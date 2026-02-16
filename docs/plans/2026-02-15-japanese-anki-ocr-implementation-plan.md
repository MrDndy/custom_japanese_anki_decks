# Japanese OCR to Anki Deck Builder Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a Python CLI that converts Japanese screenshot text into deduplicated, enriched, hierarchical Anki `.apkg` decks.

**Architecture:** Use a modular pipeline (`scan -> review -> build`) with persisted run artifacts and per-source dedup state. Keep all logic in importable service modules so a future GUI can reuse the same core pipeline. Apply TDD per module with minimal passing implementations first.

**Tech Stack:** Python 3.12, `typer`, `pydantic`, `pytest`, `rapidfuzz`, OCR engine (`pytesseract` or equivalent), tokenizer (`fugashi` + `unidic-lite`), offline dictionary source (JMdict-based), online fallback client, `genanki`.

---

### Task 1: Bootstrap project layout and CLI entrypoint

**Files:**
- Create: `pyproject.toml`
- Create: `src/jp_anki_builder/__init__.py`
- Create: `src/jp_anki_builder/cli.py`
- Create: `tests/test_cli_smoke.py`

**Step 1: Write the failing test**

```python
from typer.testing import CliRunner
from jp_anki_builder.cli import app


def test_cli_shows_help():
    result = CliRunner().invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "scan" in result.output
    assert "review" in result.output
    assert "build" in result.output
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_cli_smoke.py::test_cli_shows_help -v`
Expected: FAIL with import/module not found.

**Step 3: Write minimal implementation**

```python
# src/jp_anki_builder/cli.py
import typer

app = typer.Typer()

@app.command()
def scan() -> None:
    """Scan screenshots and produce OCR/candidate artifacts."""

@app.command()
def review() -> None:
    """Review and approve candidate words."""

@app.command()
def build() -> None:
    """Build Anki package from approved words."""

@app.command()
def run() -> None:
    """Run scan -> review -> build."""
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_cli_smoke.py::test_cli_shows_help -v`
Expected: PASS.

**Step 5: Commit**

```bash
git add pyproject.toml src/jp_anki_builder/__init__.py src/jp_anki_builder/cli.py tests/test_cli_smoke.py
git commit -m "chore: bootstrap cli project skeleton"
```

### Task 2: Implement config + storage paths

**Files:**
- Create: `src/jp_anki_builder/config.py`
- Create: `tests/test_config_paths.py`

**Step 1: Write the failing test**

```python
from jp_anki_builder.config import RunPaths


def test_run_paths_are_scoped():
    paths = RunPaths(base_dir="data", source_id="manga_a", run_id="r1")
    assert str(paths.run_dir).endswith("data/runs/r1")
    assert str(paths.source_seen_words).endswith("data/sources/manga_a/seen_words.json")
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_config_paths.py::test_run_paths_are_scoped -v`
Expected: FAIL with missing module/symbol.

**Step 3: Write minimal implementation**

```python
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class RunPaths:
    base_dir: str
    source_id: str
    run_id: str

    @property
    def run_dir(self) -> Path:
        return Path(self.base_dir) / "runs" / self.run_id

    @property
    def source_seen_words(self) -> Path:
        return Path(self.base_dir) / "sources" / self.source_id / "seen_words.json"
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_config_paths.py::test_run_paths_are_scoped -v`
Expected: PASS.

**Step 5: Commit**

```bash
git add src/jp_anki_builder/config.py tests/test_config_paths.py
git commit -m "feat: add deterministic storage path configuration"
```

### Task 3: Token filtering (particles + known words)

**Files:**
- Create: `src/jp_anki_builder/filtering.py`
- Create: `tests/test_filtering.py`

**Step 1: Write the failing test**

```python
from jp_anki_builder.filtering import filter_tokens


def test_filter_tokens_excludes_particles_and_known_words():
    tokens = ["?", "?", "??", "??"]
    known = {"??"}
    result = filter_tokens(tokens, known_words=known)
    assert result == ["?", "??"]
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_filtering.py::test_filter_tokens_excludes_particles_and_known_words -v`
Expected: FAIL with missing function.

**Step 3: Write minimal implementation**

```python
DEFAULT_PARTICLES = {"?", "?", "?", "?", "?", "?", "?", "?", "?", "?"}


def filter_tokens(tokens: list[str], known_words: set[str]) -> list[str]:
    return [t for t in tokens if t not in DEFAULT_PARTICLES and t not in known_words]
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_filtering.py::test_filter_tokens_excludes_particles_and_known_words -v`
Expected: PASS.

**Step 5: Commit**

```bash
git add src/jp_anki_builder/filtering.py tests/test_filtering.py
git commit -m "feat: add particle and known-word filtering"
```

### Task 4: Source-level dedup index

**Files:**
- Create: `src/jp_anki_builder/dedup.py`
- Create: `tests/test_dedup.py`

**Step 1: Write the failing test**

```python
from jp_anki_builder.dedup import exclude_seen


def test_exclude_seen_removes_existing_source_words():
    candidates = ["??", "??", "??"]
    seen = {"??"}
    assert exclude_seen(candidates, seen) == ["??"]
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_dedup.py::test_exclude_seen_removes_existing_source_words -v`
Expected: FAIL.

**Step 3: Write minimal implementation**

```python
def exclude_seen(candidates: list[str], seen: set[str]) -> list[str]:
    kept = []
    local_seen = set()
    for token in candidates:
        if token in seen or token in local_seen:
            continue
        local_seen.add(token)
        kept.append(token)
    return kept
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_dedup.py::test_exclude_seen_removes_existing_source_words -v`
Expected: PASS.

**Step 5: Commit**

```bash
git add src/jp_anki_builder/dedup.py tests/test_dedup.py
git commit -m "feat: add source-level dedup filtering"
```

### Task 5: Dictionary enrichment with offline-first fallback

**Files:**
- Create: `src/jp_anki_builder/enrich.py`
- Create: `tests/test_enrich.py`

**Step 1: Write the failing test**

```python
from jp_anki_builder.enrich import enrich_word


class Offline:
    def lookup(self, word):
        return None


class Online:
    def lookup(self, word):
        return {"reading": "????", "meanings": ["adventure", "quest", "journey", "venture"]}


def test_enrich_word_uses_fallback_and_caps_meanings():
    data = enrich_word("??", offline=Offline(), online=Online(), max_meanings=3)
    assert data["reading"] == "????"
    assert data["meanings"] == ["adventure", "quest", "journey"]
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_enrich.py::test_enrich_word_uses_fallback_and_caps_meanings -v`
Expected: FAIL.

**Step 3: Write minimal implementation**

```python
def enrich_word(word: str, offline, online, max_meanings: int = 3) -> dict:
    entry = offline.lookup(word) or online.lookup(word)
    if not entry:
        return {"word": word, "reading": "", "meanings": []}
    return {
        "word": word,
        "reading": entry.get("reading", ""),
        "meanings": entry.get("meanings", [])[:max_meanings],
    }
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_enrich.py::test_enrich_word_uses_fallback_and_caps_meanings -v`
Expected: PASS.

**Step 5: Commit**

```bash
git add src/jp_anki_builder/enrich.py tests/test_enrich.py
git commit -m "feat: add offline-first dictionary enrichment"
```

### Task 6: Deck naming and two-direction note mapping

**Files:**
- Create: `src/jp_anki_builder/cards.py`
- Create: `tests/test_cards.py`

**Step 1: Write the failing test**

```python
from jp_anki_builder.cards import build_deck_name, build_bidirectional_fields


def test_build_deck_name_hierarchical():
    assert build_deck_name("MangaA", "02", "07") == "MangaA::Volume02::Chapter07"


def test_build_bidirectional_fields():
    notes = build_bidirectional_fields(word="??", reading="????", meanings=["adventure"])
    assert len(notes) == 2
    assert notes[0]["front"] == "??<br>????"
    assert notes[1]["front"] == "adventure"
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_cards.py -v`
Expected: FAIL.

**Step 3: Write minimal implementation**

```python
def build_deck_name(source: str, volume: str | None, chapter: str | None) -> str:
    parts = [source]
    if volume:
        parts.append(f"Volume{volume}")
    if chapter:
        parts.append(f"Chapter{chapter}")
    return "::".join(parts)


def build_bidirectional_fields(word: str, reading: str, meanings: list[str]) -> list[dict]:
    meaning_text = "; ".join(meanings)
    a_front = f"{word}<br>{reading}" if reading else word
    return [
        {"front": a_front, "back": meaning_text},
        {"front": meaning_text, "back": a_front},
    ]
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_cards.py -v`
Expected: PASS.

**Step 5: Commit**

```bash
git add src/jp_anki_builder/cards.py tests/test_cards.py
git commit -m "feat: add deck naming and bidirectional card mapping"
```

### Task 7: Wire `scan/review/build/run` orchestration

**Files:**
- Modify: `src/jp_anki_builder/cli.py`
- Create: `src/jp_anki_builder/pipeline.py`
- Create: `tests/test_pipeline_flow.py`

**Step 1: Write the failing test**

```python
from jp_anki_builder.pipeline import Pipeline


def test_run_executes_stages_in_order():
    p = Pipeline()
    assert p.run_all() == ["scan", "review", "build"]
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_pipeline_flow.py::test_run_executes_stages_in_order -v`
Expected: FAIL.

**Step 3: Write minimal implementation**

```python
class Pipeline:
    def scan(self):
        return "scan"

    def review(self):
        return "review"

    def build(self):
        return "build"

    def run_all(self):
        return [self.scan(), self.review(), self.build()]
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_pipeline_flow.py::test_run_executes_stages_in_order -v`
Expected: PASS.

**Step 5: Commit**

```bash
git add src/jp_anki_builder/pipeline.py src/jp_anki_builder/cli.py tests/test_pipeline_flow.py
git commit -m "feat: wire pipeline stage orchestration"
```

### Task 8: End-to-end fixture test for source dedup and output artifacts

**Files:**
- Create: `tests/integration/test_source_dedup_flow.py`
- Create: `tests/fixtures/sample_ocr_ch1.json`
- Create: `tests/fixtures/sample_ocr_ch2.json`

**Step 1: Write the failing test**

```python
def test_chapter2_skips_words_seen_in_chapter1(tmp_path):
    # load fixture candidates; process ch1 then ch2 for same source
    # assert chapter2 output excludes chapter1-approved words
    assert False
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/integration/test_source_dedup_flow.py::test_chapter2_skips_words_seen_in_chapter1 -v`
Expected: FAIL (intentional placeholder).

**Step 3: Write minimal implementation**

```python
# Replace assert False with real orchestration using filtering + dedup + persisted seen_words.
# Keep fixture small and deterministic.
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/integration/test_source_dedup_flow.py::test_chapter2_skips_words_seen_in_chapter1 -v`
Expected: PASS.

**Step 5: Commit**

```bash
git add tests/integration/test_source_dedup_flow.py tests/fixtures/sample_ocr_ch1.json tests/fixtures/sample_ocr_ch2.json
git commit -m "test: verify source-level dedup across chapter runs"
```

### Task 9: Verification and documentation

**Files:**
- Modify: `README.md`
- Create: `docs/usage.md`

**Step 1: Write failing docs check task**

```text
Check that README includes install + scan/review/build/run examples and known-words workflow.
```

**Step 2: Run verification command**

Run: `rg "scan|review|build|run|known_words|Source::Volume" README.md docs/usage.md`
Expected: initially incomplete or missing.

**Step 3: Write minimal documentation**

```markdown
- install steps
- command examples
- known words and source dedup behavior
- expected artifact paths
```

**Step 4: Run final verification suite**

Run: `pytest -q`
Expected: PASS.

Run: `python -m jp_anki_builder.cli --help`
Expected: command help with scan/review/build/run.

**Step 5: Commit**

```bash
git add README.md docs/usage.md
git commit -m "docs: add mvp usage and workflow guide"
```
