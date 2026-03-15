from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import numpy as np

from jp_anki_builder.ocr import DetectedRegion
from jp_anki_builder.region_detectors.paddleocr_detector import PaddleOcrDetector

logger = logging.getLogger(__name__)


@dataclass
class NullDetector:
    """Fallback detector: returns a single region covering the entire image.

    Used by the screenshot workflow where the whole image IS the text region.
    """

    def detect(self, page_image: np.ndarray) -> list[DetectedRegion]:
        h, w = page_image.shape[:2]
        return [DetectedRegion(bbox=(0, 0, w, h), confidence=1.0)]


def build_region_detector(mode: str = "none") -> NullDetector | PaddleOcrDetector:
    """Factory — returns the appropriate RegionDetector for *mode*."""
    if mode == "none":
        return NullDetector()
    if mode == "paddleocr":
        return PaddleOcrDetector()
    raise ValueError(f"Unsupported detector: {mode!r}. Valid modes: none, paddleocr")


__all__ = ["build_region_detector", "NullDetector", "PaddleOcrDetector"]
