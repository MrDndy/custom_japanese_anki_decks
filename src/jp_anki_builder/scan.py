from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from jp_anki_builder.config import RunPaths
from jp_anki_builder.dictionary import JishoOnlineDictionary, NullOnlineDictionary, OfflineJsonDictionary
from jp_anki_builder.ocr import build_ocr_provider
from jp_anki_builder.tokenize import extract_candidates, extract_token_sequence


IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}


@dataclass
class ScanSummary:
    run_id: str
    image_count: int
    candidate_count: int
    candidates: list[str]
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
    online_dict: str = "off",
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
    offline = OfflineJsonDictionary(Path(base_dir) / "dictionaries" / "offline.json")
    if online_dict == "off":
        online = NullOnlineDictionary()
    elif online_dict == "jisho":
        online = JishoOnlineDictionary()
    else:
        raise ValueError("unsupported online dictionary mode. Use: off or jisho.")

    exists_cache: dict[str, bool] = {}

    def word_exists(word: str) -> bool:
        if word in exists_cache:
            return exists_cache[word]
        hit = offline.lookup(word, exact_match=True) is not None
        if not hit:
            hit = online.lookup(word, exact_match=True) is not None
        exists_cache[word] = hit
        return hit
    records: list[dict] = []
    all_candidates: list[str] = []

    for image_path in files:
        if hasattr(provider, "extract_text_candidates"):
            texts = provider.extract_text_candidates(image_path, top_n=8)
        else:
            texts = [provider.extract_text(image_path)]

        text = texts[0] if texts else ""
        candidates: list[str] = []
        for candidate_text in texts:
            sequence = extract_token_sequence(candidate_text)
            base = extract_candidates(candidate_text)
            candidates.extend(base)
            candidates.extend(_merge_compound_candidates(sequence, set(base), word_exists))
        candidates = list(dict.fromkeys(candidates))
        all_candidates.extend(candidates)
        records.append(
            {
                "image": str(image_path),
                "text": text,
                "alternate_texts": texts[1:6],
                "candidates": candidates,
            }
        )

    dedup_candidates = list(dict.fromkeys(all_candidates))
    payload = {
        "source": source,
        "run_id": run_id,
        "ocr_mode": ocr_mode,
        "ocr_language": ocr_language,
        "online_dict": online_dict,
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
        candidates=dedup_candidates,
        artifact_path=paths.scan_artifact,
    )


def _merge_compound_candidates(token_sequence: list[str], candidate_set: set[str], exists_fn) -> list[str]:
    merged: list[str] = []
    for i in range(len(token_sequence) - 1):
        left = token_sequence[i]
        right = token_sequence[i + 1]
        if left not in candidate_set or right not in candidate_set:
            continue
        compound = left + right
        if exists_fn(compound):
            merged.append(compound)
    return list(dict.fromkeys(merged))
