from __future__ import annotations

import json
import logging
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path

# Pre-import torch before PaddlePaddle so torch's native DLLs load first.
# On Windows, importing paddle before torch corrupts torch's DLL search state.
try:
    import torch as _torch  # noqa: F401
except ImportError:
    pass

from jp_anki_builder.config import RunPaths
from jp_anki_builder.dictionary import WordExistsCache, build_offline_dictionary, build_online_dictionary
from jp_anki_builder.normalization import get_default_normalizer
from jp_anki_builder.ocr import build_ocr_provider
from jp_anki_builder.region_detectors import build_region_detector
from jp_anki_builder.tokenize import extract_token_sequence, is_candidate_token

logger = logging.getLogger(__name__)


IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}


_REGION_TYPE_COLORS: dict[str, tuple[int, int, int]] = {
    "text": (0, 220, 0),      # green
    "sfx": (255, 140, 0),     # orange
    "caption": (0, 180, 255), # cyan
}
_REGION_DEFAULT_COLOR = (255, 255, 0)  # yellow fallback


def _save_debug_overlay(
    image_path: Path,
    ocr_text: str,
    debug_dir: Path,
    regions: list[dict] | None = None,
) -> None:
    """Save a copy of *image_path* annotated with OCR text and optional region boxes.

    When *regions* is provided (non-empty list of region dicts from scan.json),
    draws a colored bounding box and label for each region.  Falls back to
    Phase 1 text-only annotation when *regions* is None or empty.

    Silently skips (with a warning) if Pillow is unavailable or any error occurs.
    """
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError:
        logger.warning("debug overlays require Pillow; skipping (pip install Pillow)")
        return

    try:
        debug_dir.mkdir(parents=True, exist_ok=True)
        img = Image.open(image_path).convert("RGBA")
        draw = ImageDraw.Draw(img)

        if regions:
            # Phase 2: draw bounding boxes + per-region labels
            for i, region in enumerate(regions):
                x1, y1, x2, y2 = region["bbox"]
                region_type = region.get("region_type", "text")
                color = _REGION_TYPE_COLORS.get(region_type, _REGION_DEFAULT_COLOR)
                draw.rectangle([(x1, y1), (x2, y2)], outline=color, width=2)
                conf = region.get("confidence", 0.0)
                label = f"[{i}] {region_type} {conf:.2f}"
                # Shadow then label text
                for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                    draw.text((x1 + dx, y1 - 14 + dy), label, fill=(0, 0, 0, 220))
                draw.text((x1, y1 - 14), label, fill=color)
        else:
            # Phase 1: OCR text annotation only
            label = ocr_text[:200] if ocr_text else "(no text)"
            x, y = 4, 4
            for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                draw.text((x + dx, y + dy), label, fill=(0, 0, 0, 220))
            draw.text((x, y), label, fill=(255, 255, 255, 255))

        out_path = debug_dir / image_path.name
        img.convert("RGB").save(str(out_path))
        logger.debug("saved debug overlay: %s", out_path)
    except Exception as exc:
        logger.warning("could not save debug overlay for %s: %s", image_path.name, exc)


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


def _ocr_pil_image(provider, pil_image, tmp_dir: Path) -> list[str]:
    """Save *pil_image* to a temp file in *tmp_dir* and run OCR on it."""
    tmp_path = tmp_dir / "_ocr_tmp.png"
    pil_image.save(str(tmp_path))
    if hasattr(provider, "extract_text_candidates"):
        return provider.extract_text_candidates(tmp_path, top_n=8)
    return [provider.extract_text(tmp_path)]


def _merge_nearby_regions(
    regions: list,
    gap_threshold: int = 40,
    max_cluster_dim: int = 400,
) -> list:
    """Merge detected regions that are spatially close into larger clusters.

    PaddleOCR's text detection finds individual text lines/fragments rather
    than full speech bubbles.  manga-ocr produces far better results when
    given a complete bubble, so we merge nearby bounding boxes first.

    Uses a simple iterative union approach: for each region, if its bbox is
    within *gap_threshold* pixels of any existing cluster, merge it in;
    otherwise start a new cluster.

    *max_cluster_dim* caps the width or height of a merged cluster.  If a
    merge would produce a cluster larger than this on either axis, the merge
    is skipped.  This prevents separate speech bubbles that happen to be
    near each other from being combined into one huge region that confuses
    the OCR model.
    """
    from jp_anki_builder.ocr import DetectedRegion

    if not regions:
        return []

    def _expanded(bbox, gap):
        return (bbox[0] - gap, bbox[1] - gap, bbox[2] + gap, bbox[3] + gap)

    def _overlaps(a, b):
        return a[0] <= b[2] and a[2] >= b[0] and a[1] <= b[3] and a[3] >= b[1]

    def _merged_box(a, b):
        return [min(a[0], b[0]), min(a[1], b[1]),
                max(a[2], b[2]), max(a[3], b[3])]

    def _fits(box):
        return (box[2] - box[0]) <= max_cluster_dim and (box[3] - box[1]) <= max_cluster_dim

    # Each cluster is [x1, y1, x2, y2]
    clusters: list[list[int]] = []
    for region in regions:
        x1, y1, x2, y2 = region.bbox
        merged = False
        for i, cl in enumerate(clusters):
            if _overlaps(_expanded(cl, gap_threshold), (x1, y1, x2, y2)):
                candidate = _merged_box(cl, [x1, y1, x2, y2])
                if _fits(candidate):
                    clusters[i] = candidate
                    merged = True
                    break
        if not merged:
            clusters.append([x1, y1, x2, y2])

    # Repeat merging until stable (handles transitive merges)
    changed = True
    while changed:
        changed = False
        new_clusters: list[list[int]] = []
        used = [False] * len(clusters)
        for i in range(len(clusters)):
            if used[i]:
                continue
            cl = list(clusters[i])
            for j in range(i + 1, len(clusters)):
                if used[j]:
                    continue
                if _overlaps(_expanded(cl, gap_threshold), clusters[j]):
                    candidate = _merged_box(cl, clusters[j])
                    if _fits(candidate):
                        cl = candidate
                        used[j] = True
                        changed = True
            new_clusters.append(cl)
        clusters = new_clusters

    return [
        DetectedRegion(
            bbox=(cl[0], cl[1], cl[2], cl[3]),
            confidence=1.0,
            region_type="text",
        )
        for cl in clusters
    ]


_CROP_PADDING_PX = 10  # extra pixels around each region crop for OCR context


def _ocr_region_crops(provider, pil_image, regions, tmp_dir: Path) -> tuple[list[str], list[dict]]:
    """Crop each detected region, OCR it, and return aggregated texts + region records."""
    img_w, img_h = pil_image.size
    region_texts: list[str] = []
    region_records: list[dict] = []
    for j, region in enumerate(regions):
        x1, y1, x2, y2 = region.bbox
        # Add padding, clamped to image bounds
        px1 = max(0, x1 - _CROP_PADDING_PX)
        py1 = max(0, y1 - _CROP_PADDING_PX)
        px2 = min(img_w, x2 + _CROP_PADDING_PX)
        py2 = min(img_h, y2 + _CROP_PADDING_PX)
        crop = pil_image.crop((px1, py1, px2, py2))
        crop_path = tmp_dir / f"crop_{j}.png"
        crop.save(str(crop_path))
        text = provider.extract_text(crop_path)
        region_texts.append(text)
        region_records.append({
            "bbox": list(region.bbox),
            "confidence": region.confidence,
            "region_type": region.region_type,
            "text": text,
        })
    return region_texts, region_records


def _process_texts_to_candidates(texts: list[str], normalizer, word_exists) -> tuple[list[str], list[dict], list[str]]:
    """Normalize texts and extract candidates. Returns (candidates, normalized_records, surface_tokens)."""
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
    return candidates, normalized_records, primary_surface_tokens


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
    save_debug_overlays: bool = False,
    detector_mode: str = "none",
) -> ScanSummary:
    images_path = Path(images)

    # Determine if the input is a container file (CBZ, PDF, EPUB, etc.)
    _is_container = (
        images_path.is_file()
        and images_path.suffix.lower() not in IMAGE_EXTENSIONS
    )

    if _is_container:
        from jp_anki_builder.format_handlers import extract_pages
        page_results = extract_pages(images_path)
        if not page_results:
            raise ValueError(f"No pages found in: {images}")
        total_count = len(page_results)
        # Each item: (image_key, pil_image_or_None, preextracted_text_or_None)
        page_items: list[tuple[str, object, str | None]] = [
            (pr.source_file, pr.image, pr.text) for pr in page_results
        ]
        files_for_resume: list[str] = [pr.source_file for pr in page_results]
    else:
        files = _collect_images(images_path)
        if not files:
            raise ValueError(f"No image files found at: {images}")
        total_count = len(files)
        page_items = None  # path mode — existing behaviour
        files_for_resume = [str(f) for f in files]

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

    # Build the region detector (NullDetector when mode is "none")
    detector = build_region_detector(detector_mode)
    use_detector = detector_mode != "none"

    pending_count = sum(1 for k in files_for_resume if k not in done_images)
    logger.info("scanning %d image(s) (%d pending) with ocr=%s normalizer=%s detector=%s",
                total_count, pending_count, ocr_mode, normalization_method, detector_mode)

    # -----------------------------------------------------------------------
    # Path mode (existing behaviour, backward-compatible)
    # -----------------------------------------------------------------------
    if page_items is None:
        pending = [f for f in files if str(f) not in done_images]

        for image_path in pending:
            if use_detector:
                # Region-aware processing
                from PIL import Image as PILImage
                import numpy as np
                pil_img = PILImage.open(image_path).convert("RGB")
                np_img = np.array(pil_img)
                raw_regions = detector.detect(np_img)
                regions = _merge_nearby_regions(raw_regions, gap_threshold=40)
                logger.debug(
                    "merged %d raw regions → %d clusters",
                    len(raw_regions), len(regions),
                )

                with tempfile.TemporaryDirectory() as tmp_raw:
                    tmp_dir = Path(tmp_raw)
                    region_texts, region_records = _ocr_region_crops(
                        provider, pil_img, regions, tmp_dir
                    )

                text = " ".join(t for t in region_texts if t)
                texts = [text] if text else [""]
                candidates, normalized_records, surface_tokens = _process_texts_to_candidates(
                    texts, normalizer, word_exists
                )
                if save_debug_overlays:
                    _save_debug_overlay(image_path, text, paths.debug_dir,
                                        regions=region_records)
                logger.debug("image %s: %d region(s) detected candidates=%s",
                             image_path.name, len(regions), candidates)
                record = {
                    "image": str(image_path),
                    "text": text,
                    "alternate_texts": [],
                    "surface_tokens": surface_tokens,
                    "normalized_candidates": normalized_records,
                    "candidates": candidates,
                    "regions": region_records,
                }
            else:
                # Existing logic — UNCHANGED
                if hasattr(provider, "extract_text_candidates"):
                    texts = provider.extract_text_candidates(image_path, top_n=8)
                else:
                    texts = [provider.extract_text(image_path)]

                text = texts[0] if texts else ""

                if save_debug_overlays:
                    _save_debug_overlay(image_path, text, paths.debug_dir)

                candidates, normalized_records, surface_tokens = _process_texts_to_candidates(
                    texts, normalizer, word_exists
                )
                logger.debug("image %s: text=%r candidates=%s", image_path.name, text[:80], candidates)
                record = {
                    "image": str(image_path),
                    "text": text,
                    "alternate_texts": texts[1:6],
                    "surface_tokens": surface_tokens,
                    "normalized_candidates": normalized_records,
                    "candidates": candidates,
                }

            records.append(record)
            _write_scan_artifact(paths, records, source, run_id, ocr_mode, ocr_language,
                                 normalization_method, online_dict, total_count)

    # -----------------------------------------------------------------------
    # Container mode (CBZ, PDF, EPUB)
    # -----------------------------------------------------------------------
    else:
        pending_items = [(key, img, txt) for key, img, txt in page_items if key not in done_images]

        for image_key, pil_image, preextracted_text in pending_items:
            with tempfile.TemporaryDirectory() as tmp_raw:
                tmp_dir = Path(tmp_raw)

                if preextracted_text is not None:
                    # PDF text layer — skip OCR entirely
                    texts = [preextracted_text]
                    region_records_for_json: list[dict] = []
                elif use_detector:
                    # Region-aware OCR on container page image
                    import numpy as np
                    np_img = np.array(pil_image)
                    raw_regions = detector.detect(np_img)
                    regions = _merge_nearby_regions(raw_regions, gap_threshold=40)
                    region_texts, region_records_for_json = _ocr_region_crops(
                        provider, pil_image, regions, tmp_dir
                    )
                    combined = " ".join(t for t in region_texts if t)
                    texts = [combined] if combined else [""]
                else:
                    # Plain OCR on the whole page image
                    texts = _ocr_pil_image(provider, pil_image, tmp_dir)
                    region_records_for_json = []

                if save_debug_overlays and pil_image is not None:
                    # Save pil_image to a temp file so _save_debug_overlay can open it.
                    # Use a sanitized filename derived from image_key.
                    safe_name = Path(image_key.replace("::", "_")).name or "page.png"
                    if not safe_name.lower().endswith((".png", ".jpg", ".jpeg")):
                        safe_name += ".png"
                    tmp_img_path = tmp_dir / safe_name
                    pil_image.save(str(tmp_img_path))
                    text_for_overlay = texts[0] if texts else ""
                    _save_debug_overlay(
                        tmp_img_path, text_for_overlay, paths.debug_dir,
                        regions=region_records_for_json if region_records_for_json else None,
                    )

            text = texts[0] if texts else ""
            candidates, normalized_records, surface_tokens = _process_texts_to_candidates(
                texts, normalizer, word_exists
            )
            logger.debug("page %s: text=%r candidates=%s", image_key, text[:80], candidates)

            record: dict = {
                "image": image_key,
                "text": text,
                "alternate_texts": texts[1:6],
                "surface_tokens": surface_tokens,
                "normalized_candidates": normalized_records,
                "candidates": candidates,
            }
            if region_records_for_json:
                record["regions"] = region_records_for_json

            records.append(record)
            _write_scan_artifact(paths, records, source, run_id, ocr_mode, ocr_language,
                                 normalization_method, online_dict, total_count)

    # Final write (covers the case where all images were already done on resume)
    _write_scan_artifact(paths, records, source, run_id, ocr_mode, ocr_language,
                         normalization_method, online_dict, total_count)
    cache.save(paths.word_cache)

    all_candidates: list[str] = []
    for r in records:
        all_candidates.extend(r["candidates"])
    dedup_candidates = list(dict.fromkeys(all_candidates))

    return ScanSummary(
        run_id=run_id,
        image_count=total_count,
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
