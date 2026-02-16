from __future__ import annotations

import json
from dataclasses import dataclass

from jp_anki_builder.config import RunPaths
from jp_anki_builder.dedup import exclude_seen
from jp_anki_builder.filtering import filter_tokens


@dataclass
class ReviewSummary:
    run_id: str
    source: str
    initial_count: int
    approved_count: int
    review_artifact_path: str


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
) -> ReviewSummary:
    paths = RunPaths(base_dir=base_dir, source_id=source, run_id=run_id)
    if not paths.scan_artifact.exists():
        raise ValueError(f"scan artifact not found: {paths.scan_artifact}")

    scan_payload = json.loads(paths.scan_artifact.read_text(encoding="utf-8-sig"))
    candidates = scan_payload.get("candidates", [])

    known_words = _load_words_file(paths.known_words)
    seen_words = _load_seen_words(paths.source_seen_words)
    filtered = filter_tokens(candidates, known_words=known_words)
    deduped = exclude_seen(filtered, seen_words)

    excluded_manual = set(exclude or [])
    approved = [word for word in deduped if word not in excluded_manual]

    review_payload = {
        "source": source,
        "run_id": run_id,
        "initial_candidates": candidates,
        "approved_candidates": approved,
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
    )
