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

# Minimum luminance gradient (0–255) to count a pixel as an edge.
# Text strokes typically create gradients well above this; smooth
# artwork gradients stay below.
_EDGE_STRENGTH = 20.0


class OcrPipelineWorker:
    """Captures a screen region, runs OCR, caches results.

    Designed to be called from a QThread. Not Qt-aware itself —
    just a plain Python class that the Qt layer wraps.

    The cache maps content-hash → OCR text so that identical frames
    (e.g. when the user is not moving the mouse) skip re-running the
    OCR model entirely. The cache is bounded by *cache_size* entries
    and evicts the least-recently-used entry when full.
    """

    def __init__(
        self,
        capture: "ScreenCapture",
        ocr_provider,
        cache_size: int = 64,
        min_edge_density: float = 0.0,
    ) -> None:
        self._capture = capture
        self._ocr = ocr_provider
        self._cache: OrderedDict[str, str] = OrderedDict()
        self._cache_size = cache_size
        self._min_edge_density = min_edge_density

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
        """Run OCR on *frame*, preferring in-memory path when available.

        If ``min_edge_density`` is set, the frame is first checked for
        text-like content via edge density. Frames with insufficient edges
        (e.g. smooth artwork) are skipped without running the OCR model.

        If the OCR provider exposes ``extract_text_image(image)``, call it
        directly with the numpy array — no temp file needed.  Otherwise fall
        back to saving a temp PNG file and calling ``extract_text(path)``.
        """
        if self._min_edge_density > 0.0 and not _has_text_content(frame, self._min_edge_density):
            logger.debug("text-presence check failed (low edge density), skipping OCR")
            return ""

        if callable(getattr(self._ocr, "extract_text_image", None)):
            try:
                text = self._ocr.extract_text_image(frame)
                return text if isinstance(text, str) else ""
            except Exception as exc:
                logger.warning("OCR (in-memory) failed: %s", exc)
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


def _has_text_content(frame: "np.ndarray", min_density: float) -> bool:
    """Return True if *frame* likely contains text-like content.

    Computes the fraction of pixels with strong horizontal or vertical edges.
    Text strokes create sharp luminance gradients; smooth artwork or empty
    regions do not.  Uses numpy only — no additional dependencies.

    Args:
        frame: RGB numpy array, shape (H, W, 3), dtype uint8.
        min_density: minimum edge pixel fraction required (e.g. 0.03 = 3 %).

    Returns:
        True if edge density >= *min_density*, False otherwise.
    """
    import numpy as np

    if frame.ndim != 3 or frame.shape[2] < 3:
        return True  # cannot assess, assume text present

    # BT.601 grayscale weights — float32 to avoid uint8 overflow on differences.
    gray = (
        0.299 * frame[:, :, 0].astype(np.float32)
        + 0.587 * frame[:, :, 1].astype(np.float32)
        + 0.114 * frame[:, :, 2].astype(np.float32)
    )
    h_edges = np.abs(gray[:, 1:] - gray[:, :-1]) > _EDGE_STRENGTH
    v_edges = np.abs(gray[1:, :] - gray[:-1, :]) > _EDGE_STRENGTH
    edge_pixels = int(np.count_nonzero(h_edges)) + int(np.count_nonzero(v_edges))
    # Normalise: each pixel contributes to at most 2 edge maps.
    density = edge_pixels / (2 * gray.size)
    return density >= min_density


def _save_frame(frame: "np.ndarray", path: Path) -> None:
    """Write *frame* (RGB numpy array) to *path* as PNG.

    Pillow is a hard requirement for the OCR pipeline (manga-ocr and Tesseract
    both depend on it), so the import is expected to always succeed.
    """
    from PIL import Image
    Image.fromarray(frame, mode="RGB").save(path)
