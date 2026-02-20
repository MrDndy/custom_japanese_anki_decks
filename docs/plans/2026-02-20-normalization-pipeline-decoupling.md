# Normalization Pipeline Decoupling Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Decouple scan-stage surface extraction from dictionary-form normalization while preserving current CLI UX and improving internal extensibility.

**Architecture:** Keep `scan -> review -> build` command flow unchanged. Introduce a dedicated normalization layer with one active default normalizer (`RuleBasedNormalizer`) and route scan candidate generation through it. Persist normalization metadata in scan artifacts to support future accuracy tuning and eventual normalizer replacement without user-facing flags.

**Tech Stack:** Python, fugashi/unidic-lite tokenizer path, existing Typer CLI, pytest.

---

### Task 1: Add Normalization Abstraction

**Files:**
- Create: `src/jp_anki_builder/normalization.py`
- Test: `tests/test_normalization.py`

**Step 1: Write the failing test**
- Add tests for:
  - normalizer returns structured entries with `surface`, `lemma`, `method`, `confidence`, `reason`
  - current behavior parity for key examples (`奪われる -> 奪う`, `歩かされる -> 歩く`)

**Step 2: Run test to verify it fails**

Run: `.\\.venv\\Scripts\\python -m pytest tests/test_normalization.py -q`
Expected: FAIL because module/class does not exist yet.

**Step 3: Write minimal implementation**
- Add:
  - `NormalizedCandidate` dataclass
  - `Normalizer` protocol
  - `RuleBasedNormalizer` using existing tokenize-based candidate extraction
  - `get_default_normalizer()` returning the single active normalizer

**Step 4: Run test to verify it passes**

Run: `.\\.venv\\Scripts\\python -m pytest tests/test_normalization.py -q`
Expected: PASS

### Task 2: Route Scan Through Normalizer (Decoupled Stages)

**Files:**
- Modify: `src/jp_anki_builder/scan.py`
- Test: `tests/test_scan_command.py`

**Step 1: Write the failing test**
- Add scan artifact assertions for normalization metadata fields while preserving existing `candidates`.
- Adapt existing monkeypatch-based scan tests to patch the normalizer instead of directly patching `extract_candidates`.

**Step 2: Run test to verify it fails**

Run: `.\\.venv\\Scripts\\python -m pytest tests/test_scan_command.py -q`
Expected: FAIL until scan uses normalizer path.

**Step 3: Write minimal implementation**
- Keep stage order explicit in code:
  - Stage A: surface token extraction (`extract_token_sequence`)
  - Stage B: normalization (`get_default_normalizer().normalize_text(...)`)
- Build candidates from normalized lemmas.
- Persist normalization metadata in `scan.json` (record-level and top-level method marker).

**Step 4: Run test to verify it passes**

Run: `.\\.venv\\Scripts\\python -m pytest tests/test_scan_command.py -q`
Expected: PASS

### Task 3: Regression and Compatibility Verification

**Files:**
- Modify: `tests/test_tokenize.py` (only if needed for parity checks)

**Step 1: Write/adjust failing regression tests**
- Ensure prior conjugation regressions still pass through normalizer-driven scan behavior.

**Step 2: Run targeted tests**

Run:
- `.\\.venv\\Scripts\\python -m pytest tests/test_tokenize.py -q`
- `.\\.venv\\Scripts\\python -m pytest tests/test_scan_command.py -q`

Expected: PASS

**Step 3: Run full suite**

Run: `.\\.venv\\Scripts\\python -m pytest -q`
Expected: PASS

### Task 4: Docs and Final Check

**Files:**
- Modify: `README.md`

**Step 1: Add concise architecture note**
- Document that normalization is now a dedicated internal stage with one active method.
- Clarify no user-facing normalizer flag exists.

**Step 2: Verify**

Run: `.\\.venv\\Scripts\\python -m pytest -q`
Expected: PASS

