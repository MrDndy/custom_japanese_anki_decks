from __future__ import annotations

import json
import logging
import re
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

# Codecs that produce bitmap (image-based) subtitles — cannot be text-extracted.
BITMAP_SUBTITLE_CODECS = {
    "hdmv_pgs_subtitle",
    "dvd_subtitle",
    "dvb_subtitle",
    "dvb_teletext",
    "arib_caption",
}

JAPANESE_LANGUAGE_TAGS = {"jpn", "ja", "japanese", "jap"}


@dataclass
class SubtitleLine:
    text: str
    start_ms: int
    end_ms: int


@dataclass
class SubtitleTrack:
    language: str
    format: str
    lines: list[SubtitleLine]


class SubtitleExtractor:
    """Extracts subtitle tracks from video files using ffprobe/ffmpeg + pysubs2."""

    @staticmethod
    def detect_tracks(video_path: Path) -> list[dict]:
        """Use ffprobe to list subtitle tracks with language metadata."""
        try:
            result = subprocess.run(
                [
                    "ffprobe", "-v", "quiet",
                    "-print_format", "json",
                    "-show_streams",
                    "-select_streams", "s",
                    str(video_path),
                ],
                capture_output=True,
                text=True,
                timeout=30,
            )
        except FileNotFoundError:
            raise RuntimeError(
                "ffprobe not found. Install FFmpeg and ensure it is on your PATH."
            )
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError(f"ffprobe timed out on {video_path}") from exc

        try:
            data = json.loads(result.stdout)
        except json.JSONDecodeError:
            return []

        tracks = []
        for stream in data.get("streams", []):
            tags = stream.get("tags", {})
            language = (
                tags.get("language", "")
                or tags.get("LANGUAGE", "")
                or ""
            ).lower()
            codec = stream.get("codec_name", "")
            tracks.append({
                "index": stream.get("index", 0),
                "codec_name": codec,
                "language": language,
                "is_bitmap": codec in BITMAP_SUBTITLE_CODECS,
                "tags": tags,
            })
        return tracks

    @staticmethod
    def extract_track(video_path: Path, track_index: int) -> SubtitleTrack:
        """Extract a specific subtitle track using ffmpeg + pysubs2."""
        try:
            import pysubs2
        except ImportError:
            raise ImportError(
                "pysubs2 is required for subtitle extraction. "
                "Install with: pip install pysubs2"
            )

        tracks = SubtitleExtractor.detect_tracks(video_path)
        track_info = next((t for t in tracks if t["index"] == track_index), None)
        language = track_info["language"] if track_info else ""
        codec = track_info["codec_name"] if track_info else ""

        if track_info and track_info["is_bitmap"]:
            raise ValueError(
                f"Track {track_index} uses a bitmap subtitle format ({codec}). "
                "Bitmap subtitles cannot be text-extracted. "
                "Use the regular scan workflow with --images for OCR-based extraction."
            )

        with tempfile.TemporaryDirectory() as tmp_raw:
            tmp_dir = Path(tmp_raw)
            out_file = tmp_dir / "track.ass"

            try:
                proc = subprocess.run(
                    [
                        "ffmpeg", "-v", "quiet",
                        "-i", str(video_path),
                        "-map", f"0:{track_index}",
                        "-c:s", "ass",
                        str(out_file),
                    ],
                    capture_output=True,
                    timeout=120,
                )
            except FileNotFoundError:
                raise RuntimeError(
                    "ffmpeg not found. Install FFmpeg and ensure it is on your PATH."
                )
            except subprocess.TimeoutExpired as exc:
                raise RuntimeError(
                    f"ffmpeg timed out extracting track {track_index}"
                ) from exc

            if not out_file.exists():
                stderr_text = proc.stderr.decode("utf-8", errors="replace")[:500]
                raise ValueError(
                    f"Failed to extract subtitle track {track_index} from {video_path}. "
                    f"ffmpeg stderr: {stderr_text}"
                )

            subs = pysubs2.load(str(out_file))

        lines = [
            SubtitleLine(
                text=_clean_subtitle_text(event.text),
                start_ms=event.start,
                end_ms=event.end,
            )
            for event in subs
            if not event.is_comment
        ]
        lines = [line for line in lines if line.text]

        return SubtitleTrack(language=language, format=codec, lines=lines)

    @staticmethod
    def extract_japanese_track(video_path: Path) -> SubtitleTrack | None:
        """Auto-detect and extract the Japanese subtitle track.

        Prefers text-based tracks (SRT/ASS) over bitmap tracks (PGS/VobSub).
        Returns None if no Japanese text track is found.
        """
        tracks = SubtitleExtractor.detect_tracks(video_path)
        if not tracks:
            return None

        text_tracks = [t for t in tracks if not t["is_bitmap"]]
        bitmap_tracks = [t for t in tracks if t["is_bitmap"]]

        japanese_text = [
            t for t in text_tracks
            if t["language"] in JAPANESE_LANGUAGE_TAGS
        ]
        if japanese_text:
            return SubtitleExtractor.extract_track(video_path, japanese_text[0]["index"])

        japanese_bitmap = [
            t for t in bitmap_tracks
            if t["language"] in JAPANESE_LANGUAGE_TAGS
        ]
        if japanese_bitmap:
            logger.warning(
                "Found %d bitmap subtitle track(s) (PGS/VobSub) — these cannot be "
                "text-extracted. Use the regular scan workflow with --images for OCR-based "
                "extraction instead.",
                len(japanese_bitmap),
            )

        return None


def _clean_subtitle_text(text: str) -> str:
    """Strip ASS override tags, HTML tags, and normalize line breaks."""
    # Remove ASS override tags: {anything}
    text = re.sub(r"\{[^}]*\}", "", text)
    # Remove HTML-style tags
    text = re.sub(r"<[^>]+>", "", text)
    # ASS soft/hard line breaks
    text = re.sub(r"\\[Nn]", " ", text)
    return text.strip()


def run_scan_subs(
    video: str,
    source: str,
    run_id: str,
    base_dir: str = "data",
    online_dict: str = "off",
    track_index: int | None = None,
) -> object:
    """Extract Japanese subtitles from a video and produce a scan.json artifact.

    Returns a ``ScanSummary`` compatible with the existing review/build pipeline.
    The scan.json is written with ``"ocr_mode": "subtitle"`` and per-line timing metadata.
    """
    from jp_anki_builder.config import RunPaths
    from jp_anki_builder.dictionary import (
        WordExistsCache,
        build_offline_dictionary,
        build_online_dictionary,
    )
    from jp_anki_builder.normalization import get_default_normalizer
    from jp_anki_builder.scan import ScanSummary, _process_texts_to_candidates

    video_path = Path(video)
    if not video_path.exists():
        raise ValueError(f"Video file not found: {video}")

    if track_index is not None:
        track = SubtitleExtractor.extract_track(video_path, track_index)
    else:
        track = SubtitleExtractor.extract_japanese_track(video_path)
        if track is None:
            raise ValueError(
                f"No Japanese subtitle track found in {video}. "
                "Use --track-index to specify a track, or check the available tracks. "
                "Bitmap tracks (PGS/VobSub) require OCR — use the regular scan workflow instead."
            )

    if not track.lines:
        raise ValueError(f"Subtitle track extracted from {video} is empty.")

    paths = RunPaths(base_dir=base_dir, source_id=source, run_id=run_id)
    paths.run_dir.mkdir(parents=True, exist_ok=True)

    offline = build_offline_dictionary(base_dir)
    online = build_online_dictionary(online_dict)
    cache = WordExistsCache(offline, online)
    normalizer = get_default_normalizer()
    normalization_method = getattr(normalizer, "method_name", "sudachi_nlp")

    records: list[dict] = []
    all_candidates: list[str] = []

    for i, line in enumerate(track.lines):
        candidates, normalized_records, surface_tokens = _process_texts_to_candidates(
            [line.text], normalizer, cache.word_exists
        )
        record = {
            "image": f"line_{i:04d}",
            "start_ms": line.start_ms,
            "end_ms": line.end_ms,
            "text": line.text,
            "alternate_texts": [],
            "surface_tokens": surface_tokens,
            "normalized_candidates": normalized_records,
            "candidates": candidates,
        }
        records.append(record)
        all_candidates.extend(candidates)

    dedup_candidates = list(dict.fromkeys(all_candidates))

    payload = {
        "source": source,
        "run_id": run_id,
        "ocr_mode": "subtitle",
        "ocr_language": "",
        "normalization_method": normalization_method,
        "online_dict": online_dict,
        "image_count": len(track.lines),
        "video": str(video_path),
        "subtitle_language": track.language,
        "subtitle_format": track.format,
        "records": records,
        "candidates": dedup_candidates,
    }
    paths.scan_artifact.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    cache.save(paths.word_cache)

    return ScanSummary(
        run_id=run_id,
        image_count=len(track.lines),
        candidate_count=len(dedup_candidates),
        candidates=dedup_candidates,
        artifact_path=paths.scan_artifact,
    )
