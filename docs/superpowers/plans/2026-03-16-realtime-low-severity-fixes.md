# Realtime Pipeline Low-Severity Fixes

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix four remaining low-severity review issues in the realtime pipeline (redundant hashing, temp file I/O, DXcam change detection, ROI upper-bound clamp) plus repair tests broken by the earlier HIGH/MEDIUM fixes.

**Architecture:** Each fix is independent and touches a small, well-defined surface. The `ScreenCapture` protocol gains an optional `last_content_hash` property. `OcrPipelineWorker` learns to skip temp files when the OCR provider supports in-memory images. `DXcamCapture` gets hash-based duplicate detection. `_map_logical_to_physical` gains screen-size clamping. Tests broken by the removal of `_ScanThread._physical_roi` are repaired first.

**Tech Stack:** Python 3.12+, pytest, numpy, PIL, PySide6 (optional at test time)

**Test runner:** `.venv/Scripts/pytest <path> -x -q`

---

## Chunk 1: Test Repair + Redundant Hash + Temp File

### Task 1: Repair Tests Broken by Earlier Fixes

The HIGH/MEDIUM fixes removed `_ScanThread._physical_roi()` and added `_cursor_timer` to `RealtimeController`, but the tests were not updated.

**Files:**
- Modify: `tests/test_controller.py:135-156` (`_make_controller` — add `_cursor_timer = None`)
- Modify: `tests/test_controller.py:203-241` (`TestScanThreadPhysicalRoi` — remove, since `_physical_roi` no longer exists)

- [ ] **Step 1: Read the test file and understand current state**

Read `tests/test_controller.py`. Note:
- `_make_controller()` at line 155 sets `ctrl._thread = None` but does NOT set `ctrl._cursor_timer = None`, which the controller now expects.
- `TestScanThreadPhysicalRoi` (lines 203-241) calls `thread._physical_roi(500, 300)` and `thread._physical_roi(0, 0)` — this method was removed; the DPI logic now lives in `_map_logical_to_physical` (already tested by `TestMapLogicalToPhysical`).

- [ ] **Step 2: Add `_cursor_timer = None` to `_make_controller`**

In `tests/test_controller.py`, inside `_make_controller()`, add `ctrl._cursor_timer = None` after line 155 (`ctrl._thread = None`):

```python
        ctrl._thread = None
        ctrl._cursor_timer = None
        return ctrl
```

- [ ] **Step 3: Remove `TestScanThreadPhysicalRoi` class entirely**

Delete lines 203-241 (the entire `TestScanThreadPhysicalRoi` class and its `qt_app` fixture). The functionality it tested (`_physical_roi`) was inlined into `_map_logical_to_physical`, which is already covered by `TestMapLogicalToPhysical` (7 tests).

- [ ] **Step 4: Run tests to verify**

Run: `.venv/Scripts/pytest tests/test_controller.py -x -q`
Expected (PySide6 **not** installed): 10 passed, 6 skipped.
Expected (PySide6 **installed**): 15 passed, 1 skipped.

- [ ] **Step 5: Commit**

```bash
git add tests/test_controller.py
git commit -m "fix: repair test_controller tests broken by _physical_roi removal"
```

---

### Task 2: Eliminate Redundant Hash (Issue #7)

`MssCapture.grab_region()` computes an MD5 for change detection, then `OcrPipelineWorker.process_region()` computes the same MD5 on the same frame bytes for its LRU cache. The fix: expose the already-computed hash via a `last_content_hash` property on `ScreenCapture`, and have `OcrPipelineWorker` use it when available.

**Files:**
- Modify: `src/jp_anki_builder/screen_capture.py:14-21` (add `last_content_hash` to Protocol)
- Modify: `src/jp_anki_builder/screen_capture.py:62-110` (`MssCapture` — expose hash)
- Modify: `src/jp_anki_builder/screen_capture.py:24-59` (`DXcamCapture` — return `None`)
- Modify: `src/jp_anki_builder/realtime/ocr_worker.py:35-66` (`process_region` — use cached hash)
- Test: `tests/test_screen_capture.py`
- Test: `tests/test_ocr_worker.py`

- [ ] **Step 1: Write failing tests for `last_content_hash` on capture backends**

Add to `tests/test_screen_capture.py`:

```python
class TestLastContentHash:
    def test_mss_capture_has_last_content_hash_property(self):
        cap = MssCapture()
        assert cap.last_content_hash is None  # before any grab

    def test_mss_capture_hash_set_after_grab(self):
        shot = _make_mss_shot(r=42)
        cap, _ = self._make_capture_with_mock(shot)
        cap.grab_region(0, 0, 4, 3)
        assert cap.last_content_hash is not None
        assert isinstance(cap.last_content_hash, str)
        int(cap.last_content_hash, 16)  # valid hex

    def test_mss_capture_hash_none_when_unchanged(self):
        shot = _make_mss_shot()
        cap, _ = self._make_capture_with_mock(shot)
        cap.grab_region(0, 0, 4, 3)
        cap.grab_region(0, 0, 4, 3)  # returns None (unchanged)
        # Hash should still hold the value from last successful grab
        assert cap.last_content_hash is not None

    def test_dxcam_capture_last_content_hash_always_none(self):
        cap = DXcamCapture()
        assert cap.last_content_hash is None

    def _make_capture_with_mock(self, shot_array):
        """Same helper as TestMssCaptureUnit."""
        cap = MssCapture()
        mock_sct = MagicMock()
        mock_sct.grab.return_value = shot_array
        cap._sct = mock_sct
        return cap, mock_sct
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/Scripts/pytest tests/test_screen_capture.py::TestLastContentHash -x -q`
Expected: FAIL — `AttributeError: 'MssCapture' object has no attribute 'last_content_hash'`

- [ ] **Step 3: Add `last_content_hash` property to `ScreenCapture` Protocol**

In `src/jp_anki_builder/screen_capture.py`, add to the `ScreenCapture` Protocol class:

```python
@runtime_checkable
class ScreenCapture(Protocol):
    @property
    def last_content_hash(self) -> str | None:
        """Content hash from the most recent grab, or None if unavailable."""
        ...

    def grab_region(self, x: int, y: int, width: int, height: int) -> "np.ndarray | None":
        """Capture a screen region. Returns RGB numpy array or None if unchanged."""
        ...

    def close(self) -> None:
        """Release any underlying capture device or OS handle."""
        ...
```

- [ ] **Step 4: Implement `last_content_hash` on `MssCapture`**

In `MssCapture.__init__`, rename `self._last_hash` to keep it, and add the public property.

```python
class MssCapture:
    def __init__(self) -> None:
        self._sct = None
        self._last_hash: str | None = None

    @property
    def last_content_hash(self) -> str | None:
        return self._last_hash
```

The existing `grab_region` already sets `self._last_hash` — no change needed there.

- [ ] **Step 5: Implement `last_content_hash` on `DXcamCapture`**

DXcam does not compute a hash, so it always returns `None`:

```python
class DXcamCapture:
    @property
    def last_content_hash(self) -> str | None:
        return None
```

- [ ] **Step 6: Run screen_capture tests**

Run: `.venv/Scripts/pytest tests/test_screen_capture.py -x -q`
Expected: all pass

- [ ] **Step 7: Write failing test for OcrPipelineWorker using cached hash**

Add to `tests/test_ocr_worker.py`:

```python
class TestCaptureHashReuse:
    def test_skips_rehash_when_capture_provides_hash(self, monkeypatch):
        """When capture.last_content_hash is set, OcrPipelineWorker should
        use it instead of computing _content_hash itself."""
        frame = _frame(99)
        capture = MagicMock()
        capture.grab_region.return_value = frame
        capture.last_content_hash = _content_hash(frame)
        ocr = MagicMock()
        ocr.extract_text.return_value = "テスト"

        # Track calls to _content_hash — after the fix it should NOT be called
        # because the capture already provides a hash.
        import jp_anki_builder.realtime.ocr_worker as _mod
        calls: list[object] = []
        original_fn = _mod._content_hash
        def tracking_hash(f):
            calls.append(f)
            return original_fn(f)
        monkeypatch.setattr(_mod, "_content_hash", tracking_hash)

        worker = OcrPipelineWorker(capture, ocr, cache_size=64)
        worker.process_region(0, 0, 10, 10)
        assert len(calls) == 0, "_content_hash should not be called when capture provides hash"

    def test_falls_back_to_own_hash_when_capture_hash_missing(self):
        """When capture has no last_content_hash attr, worker computes its own."""
        frame = _frame(88)
        capture = MagicMock(spec=["grab_region", "close"])  # no last_content_hash
        capture.grab_region.return_value = frame
        ocr = MagicMock()
        ocr.extract_text.return_value = "漢字"

        worker = OcrPipelineWorker(capture, ocr)
        result = worker.process_region(0, 0, 10, 10)
        assert result == "漢字"
```

- [ ] **Step 8: Run test to verify it fails**

Run: `.venv/Scripts/pytest tests/test_ocr_worker.py::TestCaptureHashReuse::test_skips_rehash_when_capture_provides_hash -x -q`
Expected: FAIL — `AssertionError: _content_hash should not be called when capture provides hash` (the current code always calls `_content_hash`)

- [ ] **Step 9: Update `OcrPipelineWorker.process_region` to reuse capture hash**

In `src/jp_anki_builder/realtime/ocr_worker.py`, modify `process_region`:

```python
    def process_region(self, x: int, y: int, width: int, height: int) -> str | None:
        frame = self._capture.grab_region(x, y, width, height)
        if frame is None:
            return None

        # Reuse the content hash from the capture backend when available
        # (MssCapture already computed one for change-detection). Fall back
        # to computing our own only when the backend doesn't provide one.
        frame_hash = getattr(self._capture, "last_content_hash", None)
        if frame_hash is None:
            frame_hash = _content_hash(frame)

        if frame_hash in self._cache:
            self._cache.move_to_end(frame_hash)
            cached = self._cache[frame_hash]
            logger.debug("ocr cache hit (hash=%s...)", frame_hash[:8])
            return cached or None

        text = self._run_ocr(frame)
        self._cache_put(frame_hash, text)
        return text or None
```

- [ ] **Step 10: Run all ocr_worker tests**

Run: `.venv/Scripts/pytest tests/test_ocr_worker.py -x -q`
Expected: all pass

- [ ] **Step 11: Remove the stale comment about redundant hashing**

In `src/jp_anki_builder/realtime/ocr_worker.py`, the docstring for `process_region` mentions "Compute a content hash" at step 2. Update it to reflect the new behaviour:

```
        2. Use the capture backend's content hash if available, else compute one.
```

Also remove the old comment block (lines 52-54 in the original) about `MssCapture already computed an MD5`.

- [ ] **Step 12: Run all related tests together**

Run: `.venv/Scripts/pytest tests/test_screen_capture.py tests/test_ocr_worker.py tests/test_controller.py -x -q`
Expected: all pass

- [ ] **Step 13: Commit**

```bash
git add src/jp_anki_builder/screen_capture.py src/jp_anki_builder/realtime/ocr_worker.py tests/test_screen_capture.py tests/test_ocr_worker.py
git commit -m "perf: reuse capture backend hash in OCR pipeline, eliminating redundant MD5"
```

---

### Task 3: Skip Temp File for In-Memory-Capable OCR Providers (Issue #8)

`OcrPipelineWorker._run_ocr()` writes every frame to a temp PNG file, then passes the path to `extract_text()`. manga-ocr's `MangaOcr.__call__` natively accepts PIL `Image` objects. Adding an optional `extract_text_image()` method lets the pipeline skip the temp file for ~2-5ms savings per frame.

**Important constraint from CLAUDE.md:** "Do not rewrite the ... OCR providers". This fix adds a *new* optional method — it does not rewrite existing logic.

**Files:**
- Modify: `src/jp_anki_builder/ocr.py:115-138` (`MangaOcrProvider` — add `extract_text_image`)
- Modify: `src/jp_anki_builder/realtime/ocr_worker.py:68-82` (`_run_ocr` — prefer in-memory path)
- Test: `tests/test_ocr_worker.py`

- [ ] **Step 1: Write failing test for in-memory OCR path**

Add to `tests/test_ocr_worker.py`:

```python
class TestInMemoryOcr:
    def test_uses_extract_text_image_when_available(self):
        """When OCR provider has extract_text_image(), no temp file is created."""
        frame = _frame(50)
        capture = MagicMock()
        capture.grab_region.return_value = frame
        ocr = MagicMock()
        ocr.extract_text_image.return_value = "直接"
        # extract_text should NOT be called when extract_text_image exists
        ocr.extract_text.return_value = "ファイル"

        worker = OcrPipelineWorker(capture, ocr)
        result = worker.process_region(0, 0, 10, 10)
        assert result == "直接"
        ocr.extract_text_image.assert_called_once()
        ocr.extract_text.assert_not_called()

    def test_falls_back_to_temp_file_when_no_extract_text_image(self):
        """When OCR provider lacks extract_text_image(), temp file path is used."""
        frame = _frame(51)
        capture = MagicMock()
        capture.grab_region.return_value = frame
        ocr = MagicMock(spec=["extract_text"])  # no extract_text_image
        ocr.extract_text.return_value = "ファイル"

        worker = OcrPipelineWorker(capture, ocr)
        result = worker.process_region(0, 0, 10, 10)
        assert result == "ファイル"
        ocr.extract_text.assert_called_once()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/pytest tests/test_ocr_worker.py::TestInMemoryOcr -x -q`
Expected: FAIL

- [ ] **Step 3: Update `_run_ocr` to prefer in-memory path**

In `src/jp_anki_builder/realtime/ocr_worker.py`, replace `_run_ocr`:

```python
    def _run_ocr(self, frame: "np.ndarray") -> str:
        """Run OCR on *frame*.  Prefers in-memory path when the provider
        supports ``extract_text_image(image)``, falling back to a temp
        PNG file for providers that only accept a file path.
        """
        extract_fn = getattr(self._ocr, "extract_text_image", None)
        if extract_fn is not None:
            try:
                from PIL import Image
                image = Image.fromarray(frame, mode="RGB")
                text = extract_fn(image)
                return text if isinstance(text, str) else ""
            except Exception as exc:
                logger.warning("In-memory OCR failed: %s", exc)
                return ""

        tmp_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as fh:
                tmp_path = Path(fh.name)
            _save_frame(frame, tmp_path)
            text = self._ocr.extract_text(tmp_path)
            return text if isinstance(text, str) else ""
        except Exception as exc:
            logger.warning("OCR failed: %s", exc)
            return ""
        finally:
            if tmp_path is not None:
                tmp_path.unlink(missing_ok=True)
```

- [ ] **Step 4: Add `extract_text_image` to `MangaOcrProvider`**

In `src/jp_anki_builder/ocr.py`, add this method to `MangaOcrProvider` (after `extract_text`):

```python
    def extract_text_image(self, image) -> str:
        """OCR a PIL Image directly, skipping the file-system round-trip."""
        engine = self._get_engine()
        text = engine(image)
        if not isinstance(text, str):
            return ""
        return re.sub(r"\s+", "", text).strip()
```

Note: `manga_ocr.MangaOcr.__call__` accepts either a path string or a PIL Image.

- [ ] **Step 5: Run all ocr_worker tests**

Run: `.venv/Scripts/pytest tests/test_ocr_worker.py -x -q`
Expected: all pass

- [ ] **Step 6: Commit**

```bash
git add src/jp_anki_builder/ocr.py src/jp_anki_builder/realtime/ocr_worker.py tests/test_ocr_worker.py
git commit -m "perf: skip temp file when OCR provider supports in-memory images"
```

---

## Chunk 2: DXcam Change Detection + ROI Clamping

### Task 4: Hash-Based Change Detection for DXcamCapture (Issue #9)

**Prerequisite:** Task 2 must be completed first. `DXcamCapture` must already have a `last_content_hash` property (returning `None`), and the `ScreenCapture` Protocol must include it. Task 4 replaces the stub `last_content_hash` property on `DXcamCapture` with one backed by real hash state.

DXcam's native `None` return (signalling "no change") depends on desktop compositor timing and is unreliable — it can return a duplicate frame as non-`None`. Adding an MD5 content hash (same approach as `MssCapture`) provides deterministic change detection.

**Files:**
- Modify: `src/jp_anki_builder/screen_capture.py:24-59` (`DXcamCapture`)
- Test: `tests/test_screen_capture.py`

- [ ] **Step 1: Write failing tests for DXcam hash-based change detection**

Add to `tests/test_screen_capture.py`:

```python
class TestDXcamChangeDetection:
    def _make_dxcam_with_mock(self, grab_return=None):
        cap = DXcamCapture()
        mock_camera = MagicMock()
        mock_camera.grab.return_value = grab_return
        cap._camera = mock_camera
        return cap, mock_camera

    def test_returns_none_for_duplicate_frame(self):
        """DXcam returns frame even if content unchanged; our hash layer catches it."""
        frame = np.full((10, 10, 3), 42, dtype=np.uint8)
        cap, mock_camera = self._make_dxcam_with_mock(grab_return=frame)
        first = cap.grab_region(0, 0, 10, 10)
        assert first is not None
        # Same content again — should be detected as unchanged
        second = cap.grab_region(0, 0, 10, 10)
        assert second is None

    def test_returns_frame_after_content_change(self):
        frame1 = np.full((10, 10, 3), 10, dtype=np.uint8)
        frame2 = np.full((10, 10, 3), 20, dtype=np.uint8)
        cap, mock_camera = self._make_dxcam_with_mock()
        mock_camera.grab.side_effect = [frame1, frame2]
        first = cap.grab_region(0, 0, 10, 10)
        second = cap.grab_region(0, 0, 10, 10)
        assert first is not None
        assert second is not None

    def test_native_none_still_returns_none(self):
        """If DXcam itself returns None (frame not ready), we propagate it."""
        cap, mock_camera = self._make_dxcam_with_mock(grab_return=None)
        assert cap.grab_region(0, 0, 10, 10) is None

    def test_last_content_hash_set_after_grab(self):
        frame = np.full((10, 10, 3), 55, dtype=np.uint8)
        cap, _ = self._make_dxcam_with_mock(grab_return=frame)
        cap.grab_region(0, 0, 10, 10)
        assert cap.last_content_hash is not None
        assert isinstance(cap.last_content_hash, str)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/Scripts/pytest tests/test_screen_capture.py::TestDXcamChangeDetection -x -q`
Expected: FAIL

- [ ] **Step 3: Add hash-based change detection to `DXcamCapture`**

In `src/jp_anki_builder/screen_capture.py`, update `DXcamCapture`:

```python
class DXcamCapture:
    """Windows screen capture using DXcam (DXGI Desktop Duplication API).

    ~240 FPS capable, ~4ms latency.  An MD5 content hash is used for
    change detection because DXcam's native None return depends on
    compositor timing and can produce both false positives (returning a
    frame when nothing changed) and false negatives (None when content
    did change).
    """

    def __init__(self) -> None:
        self._camera = None
        self._last_hash: str | None = None

    @property
    def last_content_hash(self) -> str | None:
        return self._last_hash

    def _get_camera(self):
        if self._camera is not None:
            return self._camera
        try:
            import dxcam
        except ImportError as exc:
            raise RuntimeError(
                "DXcam is not installed. Install with: pip install dxcam"
            ) from exc
        self._camera = dxcam.create(output_color="RGB")
        return self._camera

    def grab_region(self, x: int, y: int, width: int, height: int) -> "np.ndarray | None":
        """Capture region. Returns RGB numpy array or None if content unchanged."""
        camera = self._get_camera()
        region = (x, y, x + width, y + height)
        frame = camera.grab(region=region)
        if frame is None:
            return None
        frame_hash = hashlib.md5(frame.tobytes(), usedforsecurity=False).hexdigest()
        if frame_hash == self._last_hash:
            return None
        self._last_hash = frame_hash
        return frame

    def close(self) -> None:
        """Release the DXGI Desktop Duplication handle."""
        if self._camera is not None:
            try:
                self._camera.release()
            except Exception:
                pass
            self._camera = None
```

- [ ] **Step 4: Update `MssCapture.last_content_hash` property**

If not already done in Task 2 (it should be), ensure `MssCapture` has the `last_content_hash` property.

- [ ] **Step 5: Run all screen_capture tests**

Run: `.venv/Scripts/pytest tests/test_screen_capture.py -x -q`
Expected: all pass

- [ ] **Step 6: Run the full test suite to check for regressions**

Run: `.venv/Scripts/pytest tests/test_screen_capture.py tests/test_ocr_worker.py tests/test_controller.py -x -q`
Expected: all pass

- [ ] **Step 7: Commit**

```bash
git add src/jp_anki_builder/screen_capture.py tests/test_screen_capture.py
git commit -m "perf: add hash-based change detection to DXcamCapture"
```

---

### Task 5: Upper-Bound ROI Clamping (Issue #10)

**Prerequisite:** Task 1 must be completed first (test repairs — `_cursor_timer = None` in `_make_controller`).

`_map_logical_to_physical` clamps coordinates to `>= 0` but not to screen bounds. While capture backends handle off-screen regions gracefully, the ROI can be smaller than expected when the cursor is near a screen edge. Adding screen-size parameters and clamping the far edge keeps the ROI within the monitor.

**Files:**
- Modify: `src/jp_anki_builder/realtime/controller.py:15-44` (`_map_logical_to_physical` — add `screen_w`/`screen_h` params)
- Modify: `src/jp_anki_builder/realtime/controller.py:95-112` (snapshot tuple gains screen dims)
- Modify: `src/jp_anki_builder/realtime/controller.py:125-135` (unpack new snapshot format in `run()`)
- Modify: `src/jp_anki_builder/realtime/controller.py:251-272` (`_sample_cursor` — include screen dims)
- Test: `tests/test_controller.py`

- [ ] **Step 1: Write failing tests for upper-bound clamping**

Add to `tests/test_controller.py` inside `TestMapLogicalToPhysical`:

```python
    def test_clamps_to_screen_upper_bound(self):
        """ROI near bottom-right edge should be pulled back within screen."""
        x, y, w, h = _map_logical_to_physical(
            cursor_x=1900, cursor_y=1060,
            roi_width=400, roi_height=200,
            origin_x=0, origin_y=0,
            dpr=1.0,
            screen_width=1920, screen_height=1080,
        )
        # Right edge must not exceed screen width
        assert x + w <= 1920
        # Bottom edge must not exceed screen height
        assert y + h <= 1080
        assert x >= 0
        assert y >= 0

    def test_no_clamp_when_screen_size_not_provided(self):
        """When screen_width/screen_height are 0 (unknown), no upper clamping."""
        x, y, w, h = _map_logical_to_physical(
            cursor_x=1900, cursor_y=1060,
            roi_width=400, roi_height=200,
            origin_x=0, origin_y=0,
            dpr=1.0,
            screen_width=0, screen_height=0,
        )
        # Without screen bounds, only lower clamp (>= 0) applies
        assert x >= 0
        assert y >= 0
        # ROI extends beyond a typical 1920x1080 screen — proves no upper clamping
        assert x + w > 1920, "ROI should extend past screen edge when no upper clamp"
        assert y + h > 1080, "ROI should extend past screen edge when no upper clamp"

    def test_clamp_with_dpr_scaling(self):
        """Upper-bound clamping should work in physical pixel coordinates."""
        x, y, w, h = _map_logical_to_physical(
            cursor_x=1500, cursor_y=850,
            roi_width=400, roi_height=200,
            origin_x=0, origin_y=0,
            dpr=1.25,
            screen_width=2400, screen_height=1350,  # 1920x1080 * 1.25
        )
        assert x + w <= 2400
        assert y + h <= 1350
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/Scripts/pytest tests/test_controller.py::TestMapLogicalToPhysical::test_clamps_to_screen_upper_bound -x -q`
Expected: FAIL — `TypeError: _map_logical_to_physical() got an unexpected keyword argument 'screen_width'`

- [ ] **Step 3: Add `screen_width` and `screen_height` to `_map_logical_to_physical`**

In `src/jp_anki_builder/realtime/controller.py`, update the function signature and body:

```python
def _map_logical_to_physical(
    cursor_x: int,
    cursor_y: int,
    roi_width: int,
    roi_height: int,
    origin_x: int,
    origin_y: int,
    dpr: float,
    screen_width: int = 0,
    screen_height: int = 0,
) -> tuple[int, int, int, int]:
    """Convert a logical-pixel cursor position to a physical-pixel mss ROI.

    The ROI is centered on the cursor.  Coordinates are clamped to >= 0
    and, when *screen_width*/*screen_height* are provided (> 0), the far
    edge is clamped to not exceed the physical screen bounds.

    Args:
        cursor_x / cursor_y: Qt logical global cursor position.
        roi_width / roi_height: desired capture size in logical pixels.
        origin_x / origin_y: top-left corner of the monitor in logical pixels
            (same value in both Qt logical and physical coordinate systems).
        dpr: device pixel ratio of the monitor (e.g. 1.25 at 125 % scaling).
        screen_width / screen_height: physical screen size in pixels.
            Pass 0 to skip upper-bound clamping.

    Returns:
        (x, y, width, height) in physical screen pixels suitable for mss.
    """
    phys_cursor_x = origin_x + int((cursor_x - origin_x) * dpr)
    phys_cursor_y = origin_y + int((cursor_y - origin_y) * dpr)
    phys_w = int(roi_width * dpr)
    phys_h = int(roi_height * dpr)
    x = max(0, phys_cursor_x - phys_w // 2)
    y = max(0, phys_cursor_y - phys_h // 2)
    if screen_width > 0 and x + phys_w > screen_width:
        x = max(0, screen_width - phys_w)
    if screen_height > 0 and y + phys_h > screen_height:
        y = max(0, screen_height - phys_h)
    return x, y, phys_w, phys_h
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/Scripts/pytest tests/test_controller.py::TestMapLogicalToPhysical -x -q`
Expected: all 10 tests pass (7 old + 3 new). Old tests pass because `screen_width`/`screen_height` default to 0 (no clamping).

- [ ] **Step 5: Expand cursor snapshot to include screen dimensions**

In `src/jp_anki_builder/realtime/controller.py`:

Update `_ScanThread._cursor_snapshot` type annotation (line 97):
```python
# Cursor snapshot: (cx, cy, origin_x, origin_y, dpr, screen_w, screen_h)
self._cursor_snapshot: tuple[int, int, int, int, float, int, int] | None = None
```

Update `update_cursor_snapshot` signature and body:
```python
def update_cursor_snapshot(
    self,
    cx: int,
    cy: int,
    origin_x: int,
    origin_y: int,
    dpr: float,
    screen_width: int,
    screen_height: int,
) -> None:
    self._cursor_snapshot = (cx, cy, origin_x, origin_y, dpr, screen_width, screen_height)
```

Update `run()` to unpack and pass screen dimensions:
```python
cx, cy, origin_x, origin_y, dpr, screen_w, screen_h = snapshot
x, y, w, h = _map_logical_to_physical(
    cx, cy, self._roi_width, self._roi_height,
    origin_x, origin_y, dpr, screen_w, screen_h,
)
```

- [ ] **Step 6: Update `_sample_cursor` to include screen dimensions**

In `_sample_cursor` inside `RealtimeController`:

```python
if screen is not None:
    origin = screen.geometry().topLeft()
    geom = screen.geometry()
    dpr = screen.devicePixelRatio()
    # Physical screen dimensions for upper-bound ROI clamping
    screen_w = int(geom.width() * dpr)
    screen_h = int(geom.height() * dpr)
    self._thread.update_cursor_snapshot(
        cx, cy, origin.x(), origin.y(), dpr, screen_w, screen_h,
    )
else:
    self._thread.update_cursor_snapshot(cx, cy, 0, 0, 1.0, 0, 0)
```

- [ ] **Step 7: Run all controller tests**

Run: `.venv/Scripts/pytest tests/test_controller.py -x -q`
Expected: all pass

- [ ] **Step 8: Run the full suite of related tests**

Run: `.venv/Scripts/pytest tests/test_controller.py tests/test_ocr_worker.py tests/test_screen_capture.py -x -q`
Expected: all pass

- [ ] **Step 9: Commit**

```bash
git add src/jp_anki_builder/realtime/controller.py tests/test_controller.py
git commit -m "fix: clamp ROI to screen bounds to prevent off-screen capture"
```
