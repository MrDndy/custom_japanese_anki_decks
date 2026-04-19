from __future__ import annotations

import json
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from jp_anki_builder.subtitle_extractor import (
    BITMAP_SUBTITLE_CODECS,
    SubtitleExtractor,
    SubtitleLine,
    SubtitleTrack,
    _clean_subtitle_text,
    run_scan_subs,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_ffprobe_output(streams: list[dict]) -> str:
    return json.dumps({"streams": streams})


def _text_stream(index: int, language: str, codec: str = "subrip") -> dict:
    return {
        "index": index,
        "codec_name": codec,
        "tags": {"language": language},
    }


def _bitmap_stream(index: int, language: str) -> dict:
    return {
        "index": index,
        "codec_name": "hdmv_pgs_subtitle",
        "tags": {"language": language},
    }


# ---------------------------------------------------------------------------
# _clean_subtitle_text
# ---------------------------------------------------------------------------

class TestCleanSubtitleText:
    def test_strips_ass_override_tags(self):
        assert _clean_subtitle_text("{\\an8}食べる") == "食べる"

    def test_strips_html_tags(self):
        assert _clean_subtitle_text("<i>飲む</i>") == "飲む"

    def test_replaces_soft_newline(self):
        result = _clean_subtitle_text("行く\\nこと")
        assert "\\n" not in result
        assert "行く" in result

    def test_plain_text_unchanged(self):
        assert _clean_subtitle_text("食べる") == "食べる"

    def test_empty_string(self):
        assert _clean_subtitle_text("") == ""

    def test_strips_whitespace(self):
        assert _clean_subtitle_text("  走る  ") == "走る"


# ---------------------------------------------------------------------------
# SubtitleExtractor.detect_tracks — mock ffprobe
# ---------------------------------------------------------------------------

class TestDetectTracks:
    def test_parses_text_track(self, tmp_path):
        fake_video = tmp_path / "test.mkv"
        fake_video.write_bytes(b"fake")

        ffprobe_out = _make_ffprobe_output([_text_stream(2, "jpn")])
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(stdout=ffprobe_out, returncode=0)
            tracks = SubtitleExtractor.detect_tracks(fake_video)

        assert len(tracks) == 1
        assert tracks[0]["language"] == "jpn"
        assert tracks[0]["codec_name"] == "subrip"
        assert tracks[0]["is_bitmap"] is False

    def test_identifies_bitmap_track(self, tmp_path):
        fake_video = tmp_path / "test.mkv"
        fake_video.write_bytes(b"fake")

        ffprobe_out = _make_ffprobe_output([_bitmap_stream(3, "jpn")])
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(stdout=ffprobe_out, returncode=0)
            tracks = SubtitleExtractor.detect_tracks(fake_video)

        assert tracks[0]["is_bitmap"] is True
        assert tracks[0]["codec_name"] == "hdmv_pgs_subtitle"

    def test_ffprobe_not_found_raises_runtime_error(self, tmp_path):
        fake_video = tmp_path / "test.mkv"
        fake_video.write_bytes(b"fake")

        with patch("subprocess.run", side_effect=FileNotFoundError):
            with pytest.raises(RuntimeError, match="ffprobe not found"):
                SubtitleExtractor.detect_tracks(fake_video)

    def test_empty_streams_returns_empty_list(self, tmp_path):
        fake_video = tmp_path / "test.mkv"
        fake_video.write_bytes(b"fake")

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(stdout='{"streams": []}', returncode=0)
            tracks = SubtitleExtractor.detect_tracks(fake_video)

        assert tracks == []

    def test_corrupt_ffprobe_output_returns_empty(self, tmp_path):
        fake_video = tmp_path / "test.mkv"
        fake_video.write_bytes(b"fake")

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(stdout="not json", returncode=0)
            tracks = SubtitleExtractor.detect_tracks(fake_video)

        assert tracks == []

    def test_timeout_raises_runtime_error(self, tmp_path):
        fake_video = tmp_path / "test.mkv"
        fake_video.write_bytes(b"fake")

        with patch("subprocess.run", side_effect=subprocess.TimeoutExpired("ffprobe", 30)):
            with pytest.raises(RuntimeError, match="timed out"):
                SubtitleExtractor.detect_tracks(fake_video)


# ---------------------------------------------------------------------------
# SubtitleExtractor.extract_japanese_track — mock both ffprobe and extract_track
# ---------------------------------------------------------------------------

class TestExtractJapaneseTrack:
    def test_selects_japanese_text_track(self, tmp_path):
        fake_video = tmp_path / "test.mkv"
        fake_video.write_bytes(b"fake")

        streams = [
            _text_stream(2, "eng"),
            _text_stream(3, "jpn"),
        ]
        ffprobe_out = _make_ffprobe_output(streams)

        fake_track = SubtitleTrack(
            language="jpn",
            format="subrip",
            lines=[SubtitleLine("食べる", 1000, 2000)],
        )

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(stdout=ffprobe_out, returncode=0)
            with patch.object(SubtitleExtractor, "extract_track", return_value=fake_track) as mock_extract:
                result = SubtitleExtractor.extract_japanese_track(fake_video)

        assert result is not None
        assert result.language == "jpn"
        mock_extract.assert_called_once_with(fake_video, 3)

    def test_skips_bitmap_returns_none_with_warning(self, tmp_path, caplog):
        fake_video = tmp_path / "test.mkv"
        fake_video.write_bytes(b"fake")

        streams = [_bitmap_stream(2, "jpn")]
        ffprobe_out = _make_ffprobe_output(streams)

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(stdout=ffprobe_out, returncode=0)
            import logging
            with caplog.at_level(logging.WARNING, logger="jp_anki_builder.subtitle_extractor"):
                result = SubtitleExtractor.extract_japanese_track(fake_video)

        assert result is None
        assert "bitmap" in caplog.text.lower() or "PGS" in caplog.text or "OCR" in caplog.text

    def test_no_japanese_track_returns_none(self, tmp_path):
        fake_video = tmp_path / "test.mkv"
        fake_video.write_bytes(b"fake")

        streams = [_text_stream(2, "eng"), _text_stream(3, "fre")]
        ffprobe_out = _make_ffprobe_output(streams)

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(stdout=ffprobe_out, returncode=0)
            result = SubtitleExtractor.extract_japanese_track(fake_video)

        assert result is None

    def test_no_streams_returns_none(self, tmp_path):
        fake_video = tmp_path / "test.mkv"
        fake_video.write_bytes(b"fake")

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(stdout='{"streams": []}', returncode=0)
            result = SubtitleExtractor.extract_japanese_track(fake_video)

        assert result is None


# ---------------------------------------------------------------------------
# run_scan_subs — unit test with fully mocked extraction
# ---------------------------------------------------------------------------

def _sudachipy_available() -> bool:
    try:
        import sudachipy  # noqa: F401
        return True
    except ImportError:
        return False


class TestRunScanSubs:
    def _make_fake_track(self) -> SubtitleTrack:
        return SubtitleTrack(
            language="jpn",
            format="subrip",
            lines=[
                SubtitleLine("食べる", 1000, 3000),
                SubtitleLine("飲む", 4000, 5500),
            ],
        )

    @pytest.mark.skipif(not _sudachipy_available(), reason="sudachipy not installed")
    def test_writes_scan_json(self, tmp_path):
        fake_video = tmp_path / "fake.mkv"
        fake_video.write_bytes(b"fake")
        with patch.object(SubtitleExtractor, "extract_japanese_track", return_value=self._make_fake_track()):
            summary = run_scan_subs(
                video=str(fake_video),
                source="testshow",
                run_id="ep01",
                base_dir=str(tmp_path),
            )

        assert summary.image_count == 2
        scan_path = tmp_path / "testshow" / "ep01" / "scan.json"
        assert scan_path.exists()
        data = json.loads(scan_path.read_text(encoding="utf-8"))
        assert data["ocr_mode"] == "subtitle"
        assert data["subtitle_language"] == "jpn"
        assert len(data["records"]) == 2

    @pytest.mark.skipif(not _sudachipy_available(), reason="sudachipy not installed")
    def test_records_have_timing(self, tmp_path):
        fake_video = tmp_path / "fake.mkv"
        fake_video.write_bytes(b"fake")
        with patch.object(SubtitleExtractor, "extract_japanese_track", return_value=self._make_fake_track()):
            run_scan_subs(
                video=str(fake_video),
                source="testshow",
                run_id="ep01",
                base_dir=str(tmp_path),
            )

        scan_path = tmp_path / "testshow" / "ep01" / "scan.json"
        data = json.loads(scan_path.read_text(encoding="utf-8"))
        record = data["records"][0]
        assert "start_ms" in record
        assert "end_ms" in record
        assert record["start_ms"] == 1000

    def test_missing_video_raises_value_error(self, tmp_path):
        with pytest.raises(ValueError, match="not found"):
            run_scan_subs(
                video=str(tmp_path / "does_not_exist.mkv"),
                source="show",
                run_id="ep01",
                base_dir=str(tmp_path),
            )

    def test_no_japanese_track_raises_value_error(self, tmp_path):
        fake_video = tmp_path / "fake.mkv"
        fake_video.write_bytes(b"fake")

        with patch.object(SubtitleExtractor, "extract_japanese_track", return_value=None):
            with pytest.raises(ValueError, match="No Japanese subtitle track"):
                run_scan_subs(
                    video=str(fake_video),
                    source="show",
                    run_id="ep01",
                    base_dir=str(tmp_path),
                )

    def test_empty_track_raises_value_error(self, tmp_path):
        fake_video = tmp_path / "fake.mkv"
        fake_video.write_bytes(b"fake")

        empty_track = SubtitleTrack(language="jpn", format="subrip", lines=[])
        with patch.object(SubtitleExtractor, "extract_japanese_track", return_value=empty_track):
            with pytest.raises(ValueError, match="empty"):
                run_scan_subs(
                    video=str(fake_video),
                    source="show",
                    run_id="ep01",
                    base_dir=str(tmp_path),
                )


# ---------------------------------------------------------------------------
# CLI smoke tests
# ---------------------------------------------------------------------------

class TestCLIScanSubs:
    def test_scan_subs_no_japanese_track(self, tmp_path):
        from typer.testing import CliRunner
        from jp_anki_builder.cli import app

        fake_video = tmp_path / "test.mkv"
        fake_video.write_bytes(b"fake")

        with patch.object(SubtitleExtractor, "extract_japanese_track", return_value=None):
            runner = CliRunner()
            result = runner.invoke(
                app,
                ["scan-subs", "--video", str(fake_video), "--data-dir", str(tmp_path)],
            )

        assert result.exit_code != 0
        assert "No Japanese subtitle track" in result.output or "WARN" in result.output

    def test_scan_subs_ffprobe_missing(self, tmp_path):
        from typer.testing import CliRunner
        from jp_anki_builder.cli import app

        fake_video = tmp_path / "test.mkv"
        fake_video.write_bytes(b"fake")

        with patch("subprocess.run", side_effect=FileNotFoundError):
            runner = CliRunner()
            result = runner.invoke(
                app,
                ["scan-subs", "--video", str(fake_video), "--data-dir", str(tmp_path)],
            )

        assert result.exit_code != 0
        assert "ffprobe" in result.output or "ERROR" in result.output
