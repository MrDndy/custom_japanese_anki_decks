"""Integration test: Subtitle extraction -> scan -> review -> build."""
from __future__ import annotations

import json
import sys
import types
from pathlib import Path
from unittest.mock import patch

import pytest


def _fake_ffprobe_output(language: str = "jpn", codec: str = "ass") -> dict:
    """Build a mock ffprobe JSON response with one subtitle stream."""
    return {
        "streams": [
            {
                "index": 2,
                "codec_name": codec,
                "codec_type": "subtitle",
                "tags": {"language": language, "title": "Japanese"},
            }
        ]
    }


def _fake_srt_content() -> str:
    return (
        "1\n00:00:01,000 --> 00:00:03,000\n"
        "魔物が出た\n\n"
        "2\n00:00:04,000 --> 00:00:06,000\n"
        "逃げろ\n\n"
        "3\n00:00:07,000 --> 00:00:09,000\n"
        "大丈夫ですか\n"
    )


@pytest.fixture()
def subtitle_env(tmp_path: Path):
    """Set up data directory + fake video file."""
    data_dir = tmp_path / "data"
    dict_dir = data_dir / "dictionaries"
    dict_dir.mkdir(parents=True)

    # Minimal JMdict
    jmdict = {
        "魔物": {"reading": "まもの", "meanings": ["demon"]},
        "逃げる": {"reading": "にげる", "meanings": ["to run away"]},
        "大丈夫": {"reading": "だいじょうぶ", "meanings": ["safe; all right"]},
    }
    (dict_dir / "offline.json").write_text(
        json.dumps(jmdict, ensure_ascii=False), encoding="utf-8"
    )

    # Fake video file (just needs to exist)
    video = tmp_path / "anime.mkv"
    video.touch()

    return {"data_dir": data_dir, "video": video}


def _sudachipy_available() -> bool:
    try:
        import sudachipy  # noqa: F401
        return True
    except ImportError:
        return False


class TestSubtitleScanIntegration:
    """Test the subtitle scan pipeline with mocked ffprobe/ffmpeg."""

    @pytest.mark.skipif(not _sudachipy_available(), reason="sudachipy not installed")
    def test_scan_subs_produces_scan_json(self, subtitle_env, monkeypatch):
        import subprocess

        video = subtitle_env["video"]
        data_dir = subtitle_env["data_dir"]

        # Mock ffprobe to return a Japanese ASS track
        ffprobe_output = json.dumps(_fake_ffprobe_output())

        # Build a fake pysubs2 module so the import succeeds without install
        _fake_events = [
            types.SimpleNamespace(text="魔物が出た", start=1000, end=3000, is_comment=False),
            types.SimpleNamespace(text="逃げろ", start=4000, end=6000, is_comment=False),
            types.SimpleNamespace(text="大丈夫ですか", start=7000, end=9000, is_comment=False),
        ]
        fake_pysubs2 = types.ModuleType("pysubs2")
        fake_pysubs2.load = lambda path, **kw: _fake_events  # type: ignore[attr-defined]
        monkeypatch.setitem(sys.modules, "pysubs2", fake_pysubs2)

        original_run = subprocess.run

        def fake_run(cmd, *args, **kwargs):
            if "ffprobe" in str(cmd[0]):
                return subprocess.CompletedProcess(
                    cmd, 0, stdout=ffprobe_output, stderr=""
                )
            elif "ffmpeg" in str(cmd[0]):
                # Write a dummy ASS file so the file-exists check passes
                out_path = cmd[-1]
                if isinstance(out_path, str) and not out_path.startswith("-"):
                    Path(out_path).write_text("[Script Info]\n", encoding="utf-8")
                return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")
            return original_run(cmd, *args, **kwargs)

        monkeypatch.setattr(subprocess, "run", fake_run)

        from jp_anki_builder.subtitle_extractor import run_scan_subs

        summary = run_scan_subs(
            video=str(video),
            source="anime",
            run_id="ep01",
            base_dir=str(data_dir),
        )

        assert summary.candidate_count > 0
        assert summary.artifact_path.exists()

        # Verify scan.json content
        scan_data = json.loads(summary.artifact_path.read_text(encoding="utf-8"))
        assert scan_data["ocr_mode"] == "subtitle"
        assert len(scan_data["records"]) > 0


class TestSubtitleScanEdgeCases:
    """Test error handling in subtitle scan."""

    def test_missing_video_raises(self, tmp_path: Path):
        from jp_anki_builder.subtitle_extractor import run_scan_subs
        with pytest.raises(ValueError, match="not found|does not exist"):
            run_scan_subs(
                video=str(tmp_path / "nonexistent.mkv"),
                source="test",
                run_id="r",
                base_dir=str(tmp_path),
            )

    def test_no_japanese_track_raises(self, subtitle_env, monkeypatch):
        import subprocess
        from jp_anki_builder.subtitle_extractor import run_scan_subs

        # Mock ffprobe to return only English track
        ffprobe_output = json.dumps(_fake_ffprobe_output(language="eng"))

        def fake_run(cmd, *args, **kwargs):
            return subprocess.CompletedProcess(
                cmd, 0, stdout=ffprobe_output, stderr=""
            )

        monkeypatch.setattr(subprocess, "run", fake_run)

        with pytest.raises((ValueError, RuntimeError)):
            run_scan_subs(
                video=str(subtitle_env["video"]),
                source="anime",
                run_id="ep01",
                base_dir=str(subtitle_env["data_dir"]),
            )
