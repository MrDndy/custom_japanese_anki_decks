from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, call

import numpy as np
import pytest

from jp_anki_builder.realtime.ocr_worker import OcrPipelineWorker, _content_hash


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _frame(value: int = 42, shape: tuple = (10, 10, 3)) -> np.ndarray:
    """Return a uniform RGB frame filled with *value*."""
    return np.full(shape, value, dtype=np.uint8)


def _make_worker(capture_returns=None, ocr_text="テスト", cache_size=64):
    """Build a worker with mocked capture and OCR provider."""
    capture = MagicMock()
    capture.grab_region.return_value = capture_returns
    ocr = MagicMock()
    ocr.extract_text.return_value = ocr_text
    worker = OcrPipelineWorker(capture, ocr, cache_size=cache_size)
    return worker, capture, ocr


# ---------------------------------------------------------------------------
# Basic behaviour
# ---------------------------------------------------------------------------

class TestProcessRegionBasic:
    def test_returns_none_when_capture_returns_none(self):
        worker, _, _ = _make_worker(capture_returns=None)
        assert worker.process_region(0, 0, 400, 200) is None

    def test_returns_ocr_text_for_new_frame(self):
        worker, _, _ = _make_worker(capture_returns=_frame(1), ocr_text="日本語")
        result = worker.process_region(0, 0, 10, 10)
        assert result == "日本語"

    def test_returns_none_for_empty_ocr_result(self):
        worker, _, _ = _make_worker(capture_returns=_frame(2), ocr_text="")
        assert worker.process_region(0, 0, 10, 10) is None

    def test_passes_coordinates_to_capture(self):
        worker, capture, _ = _make_worker(capture_returns=None)
        worker.process_region(10, 20, 300, 150)
        capture.grab_region.assert_called_once_with(10, 20, 300, 150)


# ---------------------------------------------------------------------------
# LRU cache behaviour
# ---------------------------------------------------------------------------

class TestCaching:
    def test_identical_frame_hits_cache_skips_ocr(self):
        frame = _frame(10)
        worker, capture, ocr = _make_worker(capture_returns=frame, ocr_text="cached")
        # First call runs OCR.
        worker.process_region(0, 0, 10, 10)
        # Same frame content → cache hit.
        result = worker.process_region(0, 0, 10, 10)
        assert result == "cached"
        assert ocr.extract_text.call_count == 1  # OCR ran exactly once

    def test_different_frames_run_ocr_each_time(self):
        worker, capture, ocr = _make_worker(ocr_text="text")
        capture.grab_region.side_effect = [_frame(1), _frame(2), _frame(3)]
        for _ in range(3):
            worker.process_region(0, 0, 10, 10)
        assert ocr.extract_text.call_count == 3

    def test_cache_bounded_by_cache_size(self):
        worker, capture, ocr = _make_worker(cache_size=3, ocr_text="t")
        # Feed 4 distinct frames; cache should never exceed 3 entries.
        capture.grab_region.side_effect = [_frame(v) for v in range(4)]
        for _ in range(4):
            worker.process_region(0, 0, 10, 10)
        assert len(worker._cache) <= 3

    def test_lru_eviction_keeps_recent_entries(self):
        worker, capture, ocr = _make_worker(cache_size=2, ocr_text="x")
        frames = [_frame(v) for v in range(3)]
        hashes = [_content_hash(f) for f in frames]
        capture.grab_region.side_effect = frames[:]
        for _ in range(3):
            worker.process_region(0, 0, 10, 10)
        # Frame 0 (oldest) should have been evicted; frames 1 and 2 remain.
        assert hashes[0] not in worker._cache
        assert hashes[1] in worker._cache
        assert hashes[2] in worker._cache

    def test_cache_info_reports_correct_size(self):
        worker, capture, ocr = _make_worker(cache_size=10, ocr_text="a")
        capture.grab_region.side_effect = [_frame(v) for v in range(3)]
        for _ in range(3):
            worker.process_region(0, 0, 10, 10)
        info = worker.cache_info()
        assert info["size"] == 3
        assert info["max_size"] == 10

    def test_cache_hit_after_eviction_reruns_ocr(self):
        """After frame 0 is evicted, presenting it again should re-run OCR."""
        worker, capture, ocr = _make_worker(cache_size=2, ocr_text="y")
        f0, f1, f2 = _frame(0), _frame(1), _frame(2)
        capture.grab_region.side_effect = [f0, f1, f2, f0]
        for _ in range(4):
            worker.process_region(0, 0, 10, 10)
        assert ocr.extract_text.call_count == 4  # re-ran for f0 after eviction


# ---------------------------------------------------------------------------
# Temp file cleanup
# ---------------------------------------------------------------------------

class TestTempFileCleanup:
    def test_temp_file_is_deleted_after_ocr(self, tmp_path, monkeypatch):
        created: list[Path] = []

        import tempfile as _tmpmod
        original_ntf = _tmpmod.NamedTemporaryFile

        def tracking_ntf(*args, **kwargs):
            fh = original_ntf(*args, **kwargs)
            created.append(Path(fh.name))
            return fh

        monkeypatch.setattr(_tmpmod, "NamedTemporaryFile", tracking_ntf)

        worker, capture, ocr = _make_worker(capture_returns=_frame(5), ocr_text="test")
        worker.process_region(0, 0, 10, 10)

        for p in created:
            assert not p.exists(), f"Temp file not cleaned up: {p}"

    def test_temp_file_deleted_even_when_ocr_raises(self, monkeypatch):
        created: list[Path] = []

        import tempfile as _tmpmod
        original_ntf = _tmpmod.NamedTemporaryFile

        def tracking_ntf(*args, **kwargs):
            fh = original_ntf(*args, **kwargs)
            created.append(Path(fh.name))
            return fh

        monkeypatch.setattr(_tmpmod, "NamedTemporaryFile", tracking_ntf)

        capture = MagicMock()
        capture.grab_region.return_value = _frame(6)
        ocr = MagicMock()
        ocr.extract_text.side_effect = RuntimeError("OCR failed")

        worker = OcrPipelineWorker(capture, ocr)
        result = worker.process_region(0, 0, 10, 10)

        assert result is None  # graceful fallback
        for p in created:
            assert not p.exists(), f"Temp file not cleaned up after error: {p}"


# ---------------------------------------------------------------------------
# Capture hash reuse
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Content hash helper
# ---------------------------------------------------------------------------

class TestContentHash:
    def test_same_frame_same_hash(self):
        f = _frame(7)
        assert _content_hash(f) == _content_hash(f.copy())

    def test_different_frames_different_hash(self):
        assert _content_hash(_frame(1)) != _content_hash(_frame(2))

    def test_hash_is_hex_string(self):
        h = _content_hash(_frame(0))
        assert isinstance(h, str)
        int(h, 16)  # should parse as hex without raising
