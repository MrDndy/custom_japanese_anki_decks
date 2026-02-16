from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


class OcrError(RuntimeError):
    pass


@dataclass
class SidecarOcrProvider:
    """Reads OCR text from a sibling .txt file with the same stem."""

    def extract_text(self, image_path: Path) -> str:
        sidecar = image_path.with_suffix(".txt")
        if not sidecar.exists():
            return ""
        return sidecar.read_text(encoding="utf-8")


@dataclass
class TesseractOcrProvider:
    language: str = "jpn"

    def extract_text(self, image_path: Path) -> str:
        try:
            import pytesseract
            from PIL import Image
        except ImportError as exc:
            raise OcrError(
                "Tesseract OCR mode requires 'pytesseract' and 'Pillow'. "
                "Install them, and ensure Tesseract is available on PATH."
            ) from exc

        return pytesseract.image_to_string(Image.open(image_path), lang=self.language)


def build_ocr_provider(mode: str):
    if mode == "sidecar":
        return SidecarOcrProvider()
    if mode == "tesseract":
        return TesseractOcrProvider()
    raise ValueError(f"Unsupported OCR mode: {mode}")
