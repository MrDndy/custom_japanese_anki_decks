from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass
from pathlib import Path

from jp_anki_builder.config import RunPaths
from jp_anki_builder.dictionary import WordExistsCache, build_offline_dictionary, build_online_dictionary
from jp_anki_builder.normalization import get_default_normalizer
from jp_anki_builder.ocr import build_ocr_provider
from jp_anki_builder.tokenize import extract_token_sequence, is_candidate_token

logger = logging.getLogger(__name__)


IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}


@dataclass
class ScanSummary:
    run_id: str
    image_count: int
    candidate_count: int
    candidates: list[str]
    artifact_path: Path
    resumed: bool = False


def _collect_images(images_path: Path) -> list[Path]:
    if images_path.is_file():
        return [images_path] if images_path.suffix.lower() in IMAGE_EXTENSIONS else []

    if images_path.is_dir():
        return sorted(
            p for p in images_path.rglob("*") if p.is_file() and p.suffix.lower() in IMAGE_EXTENSIONS
        )

    return []


def _load_partial_scan(scan_path: Path) -> tuple[list[dict], set[str]]:
    """Load previously completed records from a partial scan artifact."""
    if not scan_path.exists():
        return [], set()
    try:
        payload = json.loads(scan_path.read_text(encoding="utf-8-sig"))
        records = payload.get("records", [])
        done = {r["image"] for r in records}
        return records, done
    except (json.JSONDecodeError, KeyError):
        return [], set()


def _write_scan_artifact(paths: RunPaths, records: list[dict], source: str, run_id: str,
                         ocr_mode: str, ocr_language: str, normalization_method: str,
                         online_dict: str, image_count: int) -> None:
    all_candidates: list[str] = []
    for r in records:
        all_candidates.extend(r["candidates"])
    dedup_candidates = list(dict.fromkeys(all_candidates))

    payload = {
        "source": source,
        "run_id": run_id,
        "ocr_mode": ocr_mode,
        "ocr_language": ocr_language,
        "normalization_method": normalization_method,
        "online_dict": online_dict,
        "image_count": image_count,
        "records": records,
        "candidates": dedup_candidates,
    }
    paths.scan_artifact.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


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
    resume: bool = False,
) -> ScanSummary:
    images_path = Path(images)
    files = _collect_images(images_path)
    if not files:
        raise ValueError(f"No image files found at: {images}")

    paths = RunPaths(base_dir=base_dir, source_id=source, run_id=run_id)
    paths.run_dir.mkdir(parents=True, exist_ok=True)

    # Resume support: load previously completed records
    records: list[dict] = []
    done_images: set[str] = set()
    resumed = False
    if resume:
        records, done_images = _load_partial_scan(paths.scan_artifact)
        if done_images:
            resumed = True
            logger.info("resuming scan: %d image(s) already processed", len(done_images))

    provider = build_ocr_provider(
        ocr_mode,
        language=ocr_language,
        tesseract_cmd=tesseract_cmd,
        preprocess=preprocess,
    )
    offline = build_offline_dictionary(base_dir)
    online = build_online_dictionary(online_dict)
    cache = WordExistsCache(offline, online)
    if resume:
        cache.load(paths.word_cache)
    word_exists = cache.word_exists
    normalizer = get_default_normalizer()
    normalization_method = getattr(normalizer, "method_name", "sudachi_nlp")

    pending = [f for f in files if str(f) not in done_images]
    logger.info("scanning %d image(s) (%d pending) with ocr=%s normalizer=%s",
                len(files), len(pending), ocr_mode, normalization_method)

    for image_path in pending:
        if hasattr(provider, "extract_text_candidates"):
            texts = provider.extract_text_candidates(image_path, top_n=8)
        else:
            texts = [provider.extract_text(image_path)]

        text = texts[0] if texts else ""
        candidates: list[str] = []
        normalized_records: list[dict] = []
        primary_surface_tokens: list[str] = []
        for candidate_text in texts:
            sequence = extract_token_sequence(candidate_text)
            if not primary_surface_tokens:
                primary_surface_tokens = sequence
            normalized = normalizer.normalize_text(candidate_text, word_exists=word_exists)
            base = [entry.lemma for entry in normalized]
            candidates.extend(base)
            normalized_records.extend(asdict(entry) for entry in normalized)
            surface_candidates = {token for token in sequence if is_candidate_token(token)}
            candidates.extend(_merge_compound_candidates(sequence, surface_candidates, word_exists))
        candidates = list(dict.fromkeys(candidates))
        logger.debug("image %s: text=%r candidates=%s", image_path.name, text[:80], candidates)
        records.append(
            {
                "image": str(image_path),
                "text": text,
                "alternate_texts": texts[1:6],
                "surface_tokens": primary_surface_tokens,
                "normalized_candidates": normalized_records,
                "candidates": candidates,
            }
        )

        # Write incrementally after each image so partial progress is saved
        _write_scan_artifact(paths, records, source, run_id, ocr_mode, ocr_language,
                             normalization_method, online_dict, len(files))

    # Final write (also covers the case where all images were already done)
    _write_scan_artifact(paths, records, source, run_id, ocr_mode, ocr_language,
                         normalization_method, online_dict, len(files))
    cache.save(paths.word_cache)

    all_candidates: list[str] = []
    for r in records:
        all_candidates.extend(r["candidates"])
    dedup_candidates = list(dict.fromkeys(all_candidates))

    return ScanSummary(
        run_id=run_id,
        image_count=len(files),
        candidate_count=len(dedup_candidates),
        candidates=dedup_candidates,
        artifact_path=paths.scan_artifact,
        resumed=resumed,
    )


def _merge_compound_candidates(token_sequence: list[str], candidate_set: set[str], exists_fn) -> list[str]:
    merged: list[str] = []
    for i in range(len(token_sequence) - 1):
        left = token_sequence[i]
        right = token_sequence[i + 1]
        if left not in candidate_set:
            continue
        if right not in candidate_set and right not in {"ず", "ぬ"}:
            continue
        compound = left + right
        if exists_fn(compound):
            merged.append(compound)
    return list(dict.fromkeys(merged))
