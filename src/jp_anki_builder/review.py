from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass, field

from jp_anki_builder.config import RunPaths
from jp_anki_builder.filtering import DEFAULT_PARTICLES, filter_stray_furigana, is_sfx_token


@dataclass
class ReviewSummary:
    run_id: str
    source: str
    initial_count: int
    approved_count: int
    review_artifact_path: str
    excluded_known: list[str]
    excluded_particles: list[str]
    excluded_seen: list[str]
    excluded_manual: list[str]
    excluded_sfx: list[str]
    excluded_furigana: list[str]
    low_confidence_candidates: list[str]


@dataclass
class ReviewPlan:
    source: str
    run_id: str
    initial_candidates: list[str]
    filtered_candidates: list[str]
    excluded_known: list[str]
    excluded_particles: list[str]
    excluded_seen: list[str]
    excluded_sfx: list[str]
    excluded_furigana: list[str]
    confidence_meta: dict[str, dict] = field(default_factory=dict)


def _ordered_unique(words: list[str]) -> list[str]:
    seen: set[str] = set()
    unique: list[str] = []
    for word in words:
        if word in seen:
            continue
        seen.add(word)
        unique.append(word)
    return unique


def _load_words_file(path) -> set[str]:
    if not path.exists():
        return set()
    return {line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip()}


def _load_seen_words(path) -> set[str]:
    if not path.exists():
        return set()
    payload = json.loads(path.read_text(encoding="utf-8-sig"))
    return set(payload.get("seen_words", []))


def _save_seen_words(path, words: set[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"seen_words": sorted(words)}
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _append_known_words(path, words: set[str]) -> None:
    if not words:
        return
    existing = _load_words_file(path)
    merged = sorted(existing | words)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(merged) + "\n", encoding="utf-8")


def run_review(
    source: str,
    run_id: str,
    base_dir: str = "data",
    exclude: list[str] | None = None,
    save_excluded_to_known: bool = False,
    review_plan: ReviewPlan | None = None,
    exclude_sfx: bool = True,
    exclude_stray_furigana: bool = True,
    word_exists: Callable[[str], bool] | None = None,
) -> ReviewSummary:
    paths = RunPaths(base_dir=base_dir, source_id=source, run_id=run_id)
    plan = review_plan or prepare_review(
        source=source,
        run_id=run_id,
        base_dir=base_dir,
        exclude_sfx=exclude_sfx,
        exclude_stray_furigana=exclude_stray_furigana,
        word_exists=word_exists,
    )
    candidates = plan.initial_candidates
    deduped = plan.filtered_candidates
    seen_words = _load_seen_words(paths.source_seen_words)

    excluded_manual = set(exclude or [])
    approved = [word for word in deduped if word not in excluded_manual]

    # Confidence metadata for approved words only.
    approved_meta = {
        word: plan.confidence_meta[word]
        for word in approved
        if word in plan.confidence_meta
    }
    low_confidence = [
        word for word in approved
        if word in approved_meta
        and (
            approved_meta[word]["confidence"] < 0.90
            or approved_meta[word]["reason"] == "surface_fallback"
        )
    ]

    review_payload = {
        "source": source,
        "run_id": run_id,
        "initial_candidates": candidates,
        "approved_candidates": approved,
        "approved_candidates_meta": approved_meta,
        "low_confidence_candidates": low_confidence,
        "excluded_known": plan.excluded_known,
        "excluded_particles": plan.excluded_particles,
        "excluded_seen": plan.excluded_seen,
        "excluded_sfx": plan.excluded_sfx,
        "excluded_furigana": plan.excluded_furigana,
        "excluded_manual": sorted(excluded_manual),
    }
    paths.review_artifact.write_text(
        json.dumps(review_payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    updated_seen = set(seen_words)
    updated_seen.update(approved)
    _save_seen_words(paths.source_seen_words, updated_seen)

    if save_excluded_to_known:
        _append_known_words(paths.known_words, excluded_manual)

    return ReviewSummary(
        run_id=run_id,
        source=source,
        initial_count=len(candidates),
        approved_count=len(approved),
        review_artifact_path=str(paths.review_artifact),
        excluded_known=plan.excluded_known,
        excluded_particles=plan.excluded_particles,
        excluded_seen=plan.excluded_seen,
        excluded_sfx=plan.excluded_sfx,
        excluded_furigana=plan.excluded_furigana,
        low_confidence_candidates=low_confidence,
        excluded_manual=sorted(excluded_manual),
    )


def prepare_review(
    source: str,
    run_id: str,
    base_dir: str = "data",
    exclude_sfx: bool = True,
    exclude_stray_furigana: bool = True,
    word_exists: Callable[[str], bool] | None = None,
) -> ReviewPlan:
    paths = RunPaths(base_dir=base_dir, source_id=source, run_id=run_id)
    if not paths.scan_artifact.exists():
        raise ValueError(f"scan artifact not found: {paths.scan_artifact}")

    scan_payload = json.loads(paths.scan_artifact.read_text(encoding="utf-8-sig"))
    candidates = scan_payload.get("candidates", [])

    # Build lemma → best {confidence, reason} from all normalized_candidates in scan records.
    confidence_meta: dict[str, dict] = {}
    for record in scan_payload.get("records", []):
        for nc in record.get("normalized_candidates", []):
            lemma = nc.get("lemma", "")
            if not lemma:
                continue
            new_conf = float(nc.get("confidence", 0.0))
            existing = confidence_meta.get(lemma)
            if existing is None or new_conf > existing["confidence"]:
                confidence_meta[lemma] = {
                    "confidence": new_conf,
                    "reason": nc.get("reason", ""),
                }
    known_words = _load_words_file(paths.known_words)
    seen_words = _load_seen_words(paths.source_seen_words)
    local_seen: set[str] = set()
    excluded_known: list[str] = []
    excluded_particles: list[str] = []
    excluded_seen: list[str] = []
    excluded_sfx: list[str] = []
    deduped: list[str] = []

    for token in candidates:
        if token in DEFAULT_PARTICLES:
            excluded_particles.append(token)
            continue
        if token in known_words:
            excluded_known.append(token)
            continue
        if token in seen_words or token in local_seen:
            excluded_seen.append(token)
            continue
        if exclude_sfx and is_sfx_token(token, word_exists):
            excluded_sfx.append(token)
            continue

        local_seen.add(token)
        deduped.append(token)

    # Furigana filter operates on the post-loop candidate list (needs adjacency context).
    furigana_excluded: list[str] = []
    if exclude_stray_furigana:
        deduped, furigana_excluded = filter_stray_furigana(deduped)

    return ReviewPlan(
        source=source,
        run_id=run_id,
        initial_candidates=candidates,
        filtered_candidates=deduped,
        excluded_known=_ordered_unique(excluded_known),
        excluded_particles=_ordered_unique(excluded_particles),
        excluded_seen=_ordered_unique(excluded_seen),
        excluded_sfx=_ordered_unique(excluded_sfx),
        excluded_furigana=_ordered_unique(furigana_excluded),
        confidence_meta=confidence_meta,
    )
