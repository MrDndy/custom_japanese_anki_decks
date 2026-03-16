from __future__ import annotations

import hashlib
import logging
import tempfile
from collections import OrderedDict
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import numpy as np
    from jp_anki_builder.screen_capture import ScreenCapture

logger = logging.getLogger(__name__)


class OcrPipelineWorker:
    """Captures a screen region, runs OCR, caches results.

    Designed to be called from a QThread. Not Qt-aware itself —
    just a plain Python class that the Qt layer wraps.

    The cache maps content-hash → OCR text so that identical frames
    (e.g. when the user is not moving the mouse) skip re-running the
    OCR model entirely. The cache is bounded by *cache_size* entries
    and evicts the least-recently-used entry when full.
    """

    def __init__(self, capture: "ScreenCapture", ocr_provider, cache_size: int = 64) -> None:
        self._capture = capture
        self._ocr = ocr_provider
        self._cache: OrderedDict[str, str] = OrderedDict()
        self._cache_size = cache_size

    def process_region(self, x: int, y: int, width: int, height: int) -> str | None:
        """Capture and OCR a region. Returns recognized text or None if unchanged/empty.

        Steps:
        1. Grab the screen region — None from capture means content is unchanged.
        2. Use the capture backend's content hash if available, else compute one.
        3. Cache hit → return cached text without re-running OCR.
        4. Save frame to a temp PNG file (manga-ocr expects a file path).
        5. Run OCR provider on the file.
        6. Store result in LRU cache.
        7. Return recognized text (or None if OCR returned empty string).
        """
        frame = self._capture.grab_region(x, y, width, height)
        if frame is None:
            # Capture backend signals no change since last call.
            return None

        # Reuse the content hash from the capture backend when available
        # (MssCapture already computed one for change-detection). Fall back
        # to computing our own only when the backend doesn't provide a string.
        frame_hash = getattr(self._capture, "last_content_hash", None)
        if not isinstance(frame_hash, str):
            frame_hash = _content_hash(frame)

        if frame_hash in self._cache:
            # Move to end to mark as most recently used.
            self._cache.move_to_end(frame_hash)
            cached = self._cache[frame_hash]
            logger.debug("ocr cache hit (hash=%s…)", frame_hash[:8])
            return cached or None

        text = self._run_ocr(frame)
        self._cache_put(frame_hash, text)
        return text or None

    def _run_ocr(self, frame: "np.ndarray") -> str:
        """Save *frame* to a temp PNG file, run OCR, clean up, and return text."""
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

    def _cache_put(self, key: str, value: str) -> None:
        """Insert *key→value* into the LRU cache, evicting oldest if at capacity."""
        if key in self._cache:
            self._cache.move_to_end(key)
            self._cache[key] = value
        else:
            if len(self._cache) >= self._cache_size:
                self._cache.popitem(last=False)  # evict LRU (oldest)
            self._cache[key] = value

    def close(self) -> None:
        """Release the underlying screen capture device."""
        self._capture.close()

    @property
    def cache_size(self) -> int:
        return self._cache_size

    def cache_info(self) -> dict:
        return {"size": len(self._cache), "max_size": self._cache_size}


def _content_hash(frame: "np.ndarray") -> str:
    return hashlib.md5(frame.tobytes(), usedforsecurity=False).hexdigest()


def _save_frame(frame: "np.ndarray", path: Path) -> None:
    """Write *frame* (RGB numpy array) to *path* as PNG.

    Pillow is a hard requirement for the OCR pipeline (manga-ocr and Tesseract
    both depend on it), so the import is expected to always succeed.
    """
    from PIL import Image
    Image.fromarray(frame, mode="RGB").save(path)
