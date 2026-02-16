from __future__ import annotations

import re
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
class MangaOcrProvider:
    _engine = None

    @classmethod
    def _get_engine(cls):
        if cls._engine is not None:
            return cls._engine
        try:
            from manga_ocr import MangaOcr
        except ImportError as exc:
            raise OcrError(
                "manga-ocr mode requires the 'manga-ocr' package. Install with: "
                ".\\.venv\\Scripts\\python -m pip install manga-ocr"
            ) from exc
        cls._engine = MangaOcr()
        return cls._engine

    def extract_text(self, image_path: Path) -> str:
        engine = self._get_engine()
        text = engine(str(image_path))
        if not isinstance(text, str):
            return ""
        return re.sub(r"\s+", "", text).strip()


@dataclass
class OcrCandidate:
    text: str
    confidence: float
    config: str
    preprocessed: bool
    language: str = ""


@dataclass
class TesseractOcrProvider:
    language: str = "jpn"
    tesseract_cmd: str | None = None
    preprocess: bool = True

    def extract_text(self, image_path: Path) -> str:
        candidates = self.extract_text_candidates(image_path, top_n=1)
        return candidates[0] if candidates else ""

    def extract_text_candidates(self, image_path: Path, top_n: int = 8) -> list[str]:
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
        variants = self._preprocess_variants(image) if self.preprocess else [("orig", image)]
        configs = ["--oem 1 --psm 6", "--oem 1 --psm 7", "--oem 1 --psm 11"]
        languages = self._language_variants(self.language)
        candidates: list[OcrCandidate] = []
        errors: list[Exception] = []

        for config in configs:
            for lang in languages:
                for variant_name, variant in variants:
                    try:
                        candidate = self._ocr_candidate(
                            pytesseract,
                            variant,
                            config,
                            preprocessed=(variant_name != "orig"),
                            language=lang,
                        )
                    except Exception as exc:
                        errors.append(exc)
                        continue
                    if candidate.text:
                        candidates.append(candidate)

        if not candidates:
            if errors:
                self._raise_with_context(errors[-1])
            return []

        # Highest-scoring text first, unique by normalized output.
        ranked = sorted(candidates, key=self._score_candidate, reverse=True)
        seen: set[str] = set()
        texts: list[str] = []
        for item in ranked:
            if item.text in seen:
                continue
            seen.add(item.text)
            texts.append(item.text)
            if len(texts) >= top_n:
                break
        return texts

    @staticmethod
    def _preprocess_variants(image):
        # Try multiple threshold variants; different fonts/backgrounds behave differently.
        width, height = image.size
        gray = image.convert("L")
        up2 = gray.resize((width * 2, height * 2))
        return [
            ("orig", image),
            ("up2_thr140", up2.point(lambda p: 255 if p > 140 else 0)),
            ("up2_thr160", up2.point(lambda p: 255 if p > 160 else 0)),
            ("up2_thr180", up2.point(lambda p: 255 if p > 180 else 0)),
        ]

    @staticmethod
    def _normalize_text(text: str) -> str:
        compact = re.sub(r"\s+", " ", text).strip()
        return re.sub(
            r"(?<=[\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff])\s+(?=[\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff])",
            "",
            compact,
        )

    @staticmethod
    def _language_variants(language: str) -> list[str]:
        variants = [language]
        if language == "jpn":
            variants.append("jpn+jpn_vert")
        return variants

    def _ocr_candidate(self, pytesseract, image, config: str, preprocessed: bool, language: str) -> OcrCandidate:
        data = pytesseract.image_to_data(
            image,
            lang=language,
            config=config,
            output_type=pytesseract.Output.DICT,
        )
        tokens: list[str] = []
        confs: list[float] = []

        for token, conf in zip(data.get("text", []), data.get("conf", []), strict=False):
            token = (token or "").strip()
            if not token:
                continue
            tokens.append(token)
            try:
                val = float(conf)
            except (TypeError, ValueError):
                continue
            if val >= 0:
                confs.append(val)

        text = self._normalize_text(" ".join(tokens))
        avg_conf = sum(confs) / len(confs) if confs else 0.0
        return OcrCandidate(
            text=text,
            confidence=avg_conf,
            config=config,
            preprocessed=preprocessed,
            language=language,
        )

    @staticmethod
    def _score_candidate(candidate: OcrCandidate) -> float:
        text = candidate.text
        no_space = re.sub(r"\s+", "", text)
        if not no_space:
            return -1e9

        jp_chars = len(re.findall(r"[\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff]", no_space))
        ascii_noise = len(re.findall(r"[A-Za-z0-9]", no_space))
        question_marks = text.count("?")
        single_hiragana = 1 if re.fullmatch(r"[\u3040-\u309f]", no_space) else 0
        very_short = 1 if len(no_space) <= 1 else 0

        # Favor high-confidence Japanese-heavy output, penalize obvious noise.
        return (
            candidate.confidence * 0.35
            + jp_chars * 4.0
            + len(no_space) * 2.0
            - ascii_noise * 1.5
            - question_marks * 2.0
            - single_hiragana * 12.0
            - very_short * 8.0
        )

    def _raise_with_context(self, exc: Exception) -> None:
        message = str(exc)
        if "TesseractNotFoundError" in exc.__class__.__name__ or "is not installed" in message:
            raise OcrError(
                "Tesseract executable not found. Install Tesseract OCR and add it to PATH, "
                "or pass --tesseract-cmd with the full executable path."
            ) from exc
        if "Failed loading language" in message or ".traineddata" in message:
            raise OcrError(
                f"Tesseract language data not available for '{self.language}'. "
                "Install matching traineddata files in your tessdata directory."
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
    if mode == "manga-ocr":
        return MangaOcrProvider()
    if mode == "tesseract":
        return TesseractOcrProvider(
            language=language,
            tesseract_cmd=tesseract_cmd,
            preprocess=preprocess,
        )
    raise ValueError(f"Unsupported OCR mode: {mode}")
