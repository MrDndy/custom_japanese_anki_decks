from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from jp_anki_builder.config import RunPaths
from jp_anki_builder.ocr import build_ocr_provider
from jp_anki_builder.tokenize import extract_candidates


IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}


@dataclass
class ScanSummary:
    run_id: str
    image_count: int
    candidate_count: int
    artifact_path: Path


def _collect_images(images_path: Path) -> list[Path]:
    if images_path.is_file():
        return [images_path] if images_path.suffix.lower() in IMAGE_EXTENSIONS else []

    if images_path.is_dir():
        return sorted(
            p for p in images_path.rglob("*") if p.is_file() and p.suffix.lower() in IMAGE_EXTENSIONS
        )

    return []


def run_scan(
    images: str,
    source: str,
    run_id: str,
    base_dir: str = "data",
    ocr_mode: str = "sidecar",
    ocr_language: str = "jpn",
    tesseract_cmd: str | None = None,
    preprocess: bool = True,
) -> ScanSummary:
    images_path = Path(images)
    files = _collect_images(images_path)
    if not files:
        raise ValueError(f"No image files found at: {images}")

    paths = RunPaths(base_dir=base_dir, source_id=source, run_id=run_id)
    paths.run_dir.mkdir(parents=True, exist_ok=True)

    provider = build_ocr_provider(
        ocr_mode,
        language=ocr_language,
        tesseract_cmd=tesseract_cmd,
        preprocess=preprocess,
    )
    records: list[dict] = []
    all_candidates: list[str] = []

    for image_path in files:
        text = provider.extract_text(image_path)
        candidates = extract_candidates(text)
        all_candidates.extend(candidates)
        records.append(
            {
                "image": str(image_path),
                "text": text,
                "candidates": candidates,
            }
        )

    dedup_candidates = list(dict.fromkeys(all_candidates))
    payload = {
        "source": source,
        "run_id": run_id,
        "ocr_mode": ocr_mode,
        "ocr_language": ocr_language,
        "image_count": len(files),
        "records": records,
        "candidates": dedup_candidates,
    }

    paths.scan_artifact.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    return ScanSummary(
        run_id=run_id,
        image_count=len(files),
        candidate_count=len(dedup_candidates),
        artifact_path=paths.scan_artifact,
    )
