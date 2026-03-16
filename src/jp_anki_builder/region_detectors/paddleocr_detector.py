"""PaddleOCR-based RegionDetector implementation for full-page manga parsing."""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import numpy as np

from jp_anki_builder.ocr import DetectedRegion

logger = logging.getLogger(__name__)

try:
    from paddleocr import PaddleOCR as _PaddleOCR  # noqa: F401
    _PADDLEOCR_AVAILABLE = True
except ImportError:
    _PADDLEOCR_AVAILABLE = False


def _build_paddleocr():
    """Construct the PaddleOCR model (detection only, no recognition)."""
    from paddleocr import PaddleOCR
    return PaddleOCR(use_angle_cls=False, lang="japan", rec=False, show_log=False)


@dataclass
class PaddleOcrDetector:
    """RegionDetector implementation using PaddleOCR text detection."""

    _engine: object = field(default=None, init=False, repr=False)

    def _get_engine(self):
        if self._engine is not None:
            return self._engine
        if not _PADDLEOCR_AVAILABLE:
            raise RuntimeError(
                "paddleocr is required for region detection. "
                "Install with: pip install paddlepaddle paddleocr"
            )
        logger.info("initializing PaddleOCR detection model (first use)…")
        self._engine = _build_paddleocr()
        return self._engine

    def detect(self, page_image: np.ndarray) -> list[DetectedRegion]:
        engine = self._get_engine()
        result = engine.ocr(page_image, rec=False)
        regions: list[DetectedRegion] = []
        if not result or not result[0]:
            return regions
        for item in result[0]:
            if item is None:
                continue
            # PaddleOCR returns: [[x1,y1],[x2,y1],[x2,y2],[x1,y2]], confidence
            # Older versions may omit the confidence value, so unpack defensively.
            if isinstance(item, (list, tuple)) and len(item) == 2:
                quad, confidence = item
                confidence = float(confidence)
            else:
                quad = item
                confidence = 1.0
            xs = [pt[0] for pt in quad]
            ys = [pt[1] for pt in quad]
            bbox = (int(min(xs)), int(min(ys)), int(max(xs)), int(max(ys)))
            regions.append(DetectedRegion(bbox=bbox, confidence=confidence))
        return regions
