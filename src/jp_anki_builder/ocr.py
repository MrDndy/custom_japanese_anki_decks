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
        return sidecar.read_text(encoding="utf-8-sig")


@dataclass
class TesseractOcrProvider:
    language: str = "jpn"
    tesseract_cmd: str | None = None
    preprocess: bool = True

    def extract_text(self, image_path: Path) -> str:
        try:
            import pytesseract
            from PIL import Image
        except ImportError as exc:
            raise OcrError(
                "Tesseract OCR mode requires 'pytesseract' and 'Pillow'. "
                "Install them, and ensure Tesseract is available on PATH."
            ) from exc

        if self.tesseract_cmd:
            pytesseract.pytesseract.tesseract_cmd = self.tesseract_cmd

        image = Image.open(image_path)
        if self.preprocess:
            # Basic thresholding often improves JP text OCR from screenshots.
            image = image.convert("L").point(lambda p: 255 if p > 180 else 0)

        try:
            return pytesseract.image_to_string(image, lang=self.language)
        except Exception as exc:
            message = str(exc)
            if "TesseractNotFoundError" in exc.__class__.__name__ or "is not installed" in message:
                raise OcrError(
                    "Tesseract executable not found. Install Tesseract OCR and add it to PATH, "
                    "or pass --tesseract-cmd with the full executable path."
                ) from exc
            raise OcrError(f"Tesseract OCR failed: {message}") from exc


def build_ocr_provider(
    mode: str,
    language: str = "jpn",
    tesseract_cmd: str | None = None,
    preprocess: bool = True,
):
    if mode == "sidecar":
        return SidecarOcrProvider()
    if mode == "tesseract":
        return TesseractOcrProvider(
            language=language,
            tesseract_cmd=tesseract_cmd,
            preprocess=preprocess,
        )
    raise ValueError(f"Unsupported OCR mode: {mode}")
