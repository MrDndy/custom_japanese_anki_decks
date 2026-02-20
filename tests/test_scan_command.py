from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from jp_anki_builder.cli import app
from jp_anki_builder.normalization import NormalizedCandidate
from jp_anki_builder.ocr import OcrError


class _FakeNormalizer:
    def __init__(self, words: list[str]):
        self._words = words
        self.method_name = "rule_based"

    def normalize_text(self, text: str, word_exists=None) -> list[NormalizedCandidate]:
        return [
            NormalizedCandidate(
                surface=word,
                lemma=word,
                method="rule_based",
                confidence=0.9,
                reason="lemma_normalized",
            )
            for word in self._words
        ]


def test_scan_writes_artifact_from_sidecar_ocr(tmp_path: Path):
    images_dir = tmp_path / "images"
    images_dir.mkdir()
    image = images_dir / "panel1.png"
    image.write_bytes(b"fake")
    image.with_suffix(".txt").write_text("\u5192\u967a\u306b\u884c\u304f \u52c7\u8005", encoding="utf-8")

    data_dir = tmp_path / "data"

    result = CliRunner().invoke(
        app,
        [
            "scan",
            "--images",
            str(images_dir),
            "--source",
            "manga-a",
            "--run-id",
            "manga-a-ch01",
            "--data-dir",
            str(data_dir),
            "--ocr-mode",
            "sidecar",
        ],
    )

    assert result.exit_code == 0
    assert "[SCAN]" in result.output
    assert "[INFO] Candidate preview:" in result.output
    assert "冒険" in result.output
    artifact = data_dir / "manga-a" / "manga-a-ch01" / "scan.json"
    assert artifact.exists()

    payload = json.loads(artifact.read_text(encoding="utf-8"))
    assert payload["source"] == "manga-a"
    assert payload["image_count"] == 1
    assert "\u5192\u967a" in payload["candidates"]
    assert "\u884c\u304f" in payload["candidates"]
    assert "\u52c7\u8005" in payload["candidates"]
    assert payload["normalization_method"] == "rule_based"
    assert payload["records"][0]["surface_tokens"]
    assert payload["records"][0]["normalized_candidates"]


def test_scan_errors_when_no_images_found(tmp_path: Path):
    missing = tmp_path / "missing"

    result = CliRunner().invoke(
        app,
        [
            "scan",
            "--images",
            str(missing),
            "--source",
            "manga-a",
            "--run-id",
            "manga-a-empty",
        ],
    )

    assert result.exit_code != 0
    assert "No image files found" in result.output


def test_scan_sidecar_supports_utf8_bom(tmp_path: Path):
    images_dir = tmp_path / "images"
    images_dir.mkdir()
    image = images_dir / "panel1.png"
    image.write_bytes(b"fake")
    image.with_suffix(".txt").write_text("\u5192\u967a", encoding="utf-8-sig")

    result = CliRunner().invoke(
        app,
        [
            "scan",
            "--images",
            str(images_dir),
            "--source",
            "manga-a",
            "--run-id",
            "manga-a-ch02",
            "--data-dir",
            str(tmp_path / "data"),
            "--ocr-mode",
            "sidecar",
        ],
    )

    assert result.exit_code == 0


def test_scan_surfaces_ocr_errors(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    from jp_anki_builder import scan as scan_module

    images_dir = tmp_path / "images"
    images_dir.mkdir()
    image = images_dir / "panel1.png"
    image.write_bytes(b"fake")

    class BrokenProvider:
        def extract_text(self, image_path: Path) -> str:
            raise OcrError("tesseract executable not found")

    monkeypatch.setattr(
        scan_module,
        "build_ocr_provider",
        lambda mode, language="jpn", tesseract_cmd=None, preprocess=True: BrokenProvider(),
    )

    result = CliRunner().invoke(
        app,
        [
            "scan",
            "--images",
            str(images_dir),
            "--source",
            "manga-a",
            "--run-id",
            "manga-a-ch03",
            "--ocr-mode",
            "tesseract",
        ],
    )

    assert result.exit_code != 0
    assert "tesseract executable not found" in result.output


def test_scan_adds_compound_candidates_from_offline_dictionary(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    from jp_anki_builder import scan as scan_module

    images_dir = tmp_path / "images"
    images_dir.mkdir()
    image = images_dir / "panel1.png"
    image.write_bytes(b"fake")
    image.with_suffix(".txt").write_text("ignored", encoding="utf-8")

    data_dir = tmp_path / "data"
    dict_dir = data_dir / "dictionaries"
    dict_dir.mkdir(parents=True)
    (dict_dir / "offline.json").write_text(
        json.dumps({"無駄飯食い": {"reading": "むだめしくい", "meanings": ["good-for-nothing"]}}, ensure_ascii=False),
        encoding="utf-8",
    )

    monkeypatch.setattr(scan_module, "extract_token_sequence", lambda text: ["無駄飯", "食い"])
    monkeypatch.setattr(scan_module, "get_default_normalizer", lambda: _FakeNormalizer(["無駄飯", "食い"]))

    result = CliRunner().invoke(
        app,
        [
            "scan",
            "--images",
            str(images_dir),
            "--source",
            "miharu",
            "--run-id",
            "ch00",
            "--data-dir",
            str(data_dir),
            "--ocr-mode",
            "sidecar",
        ],
    )

    assert result.exit_code == 0
    payload = json.loads((data_dir / "miharu" / "ch00" / "scan.json").read_text(encoding="utf-8"))
    assert "無駄飯" in payload["candidates"]
    assert "食い" in payload["candidates"]
    assert "無駄飯食い" in payload["candidates"]


def test_scan_adds_compound_candidates_with_online_fallback(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    from jp_anki_builder import scan as scan_module

    images_dir = tmp_path / "images"
    images_dir.mkdir()
    image = images_dir / "panel1.png"
    image.write_bytes(b"fake")
    image.with_suffix(".txt").write_text("ignored", encoding="utf-8")

    data_dir = tmp_path / "data"
    dict_dir = data_dir / "dictionaries"
    dict_dir.mkdir(parents=True)
    (dict_dir / "offline.json").write_text("{}", encoding="utf-8")

    monkeypatch.setattr(scan_module, "extract_token_sequence", lambda text: ["無駄飯", "食い"])
    monkeypatch.setattr(scan_module, "get_default_normalizer", lambda: _FakeNormalizer(["無駄飯", "食い"]))

    class FakeOnline:
        def lookup(self, word, exact_match: bool = False):
            if word == "無駄飯食い":
                return {"reading": "むだめしくい", "meanings": ["good-for-nothing"]}
            return None

    monkeypatch.setattr(scan_module, "JishoOnlineDictionary", lambda: FakeOnline())

    result = CliRunner().invoke(
        app,
        [
            "scan",
            "--images",
            str(images_dir),
            "--source",
            "miharu",
            "--run-id",
            "ch01",
            "--data-dir",
            str(data_dir),
            "--ocr-mode",
            "sidecar",
            "--online-dict",
            "jisho",
        ],
    )

    assert result.exit_code == 0
    payload = json.loads((data_dir / "miharu" / "ch01" / "scan.json").read_text(encoding="utf-8"))
    assert "無駄飯食い" in payload["candidates"]


def test_scan_does_not_merge_across_particle_boundary(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    from jp_anki_builder import scan as scan_module

    images_dir = tmp_path / "images"
    images_dir.mkdir()
    image = images_dir / "panel1.png"
    image.write_bytes(b"fake")
    image.with_suffix(".txt").write_text("ignored", encoding="utf-8")

    data_dir = tmp_path / "data"
    dict_dir = data_dir / "dictionaries"
    dict_dir.mkdir(parents=True)
    # Even if this key exists, a merge should not be formed across particle boundaries.
    (dict_dir / "offline.json").write_text(
        json.dumps({"足痛い": {"reading": "あしいたい", "meanings": ["n/a"]}}, ensure_ascii=False),
        encoding="utf-8",
    )

    monkeypatch.setattr(scan_module, "extract_token_sequence", lambda text: ["足", "が", "痛い"])
    monkeypatch.setattr(scan_module, "get_default_normalizer", lambda: _FakeNormalizer(["足", "痛い"]))

    result = CliRunner().invoke(
        app,
        [
            "scan",
            "--images",
            str(images_dir),
            "--source",
            "miharu",
            "--run-id",
            "ch02",
            "--data-dir",
            str(data_dir),
            "--ocr-mode",
            "sidecar",
        ],
    )

    assert result.exit_code == 0
    payload = json.loads((data_dir / "miharu" / "ch02" / "scan.json").read_text(encoding="utf-8"))
    assert "足" in payload["candidates"]
    assert "痛い" in payload["candidates"]
    assert "足痛い" not in payload["candidates"]


def test_scan_merges_lexicalized_negative_compound_when_dictionary_has_it(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    from jp_anki_builder import scan as scan_module

    images_dir = tmp_path / "images"
    images_dir.mkdir()
    image = images_dir / "panel1.png"
    image.write_bytes(b"fake")
    image.with_suffix(".txt").write_text("ignored", encoding="utf-8")

    data_dir = tmp_path / "data"
    dict_dir = data_dir / "dictionaries"
    dict_dir.mkdir(parents=True)
    (dict_dir / "offline.json").write_text(
        json.dumps({"役立たず": {"reading": "やくだたず", "meanings": ["good-for-nothing"]}}, ensure_ascii=False),
        encoding="utf-8",
    )

    monkeypatch.setattr(scan_module, "extract_token_sequence", lambda text: ["役立た", "ず"])
    monkeypatch.setattr(scan_module, "get_default_normalizer", lambda: _FakeNormalizer(["役立た"]))

    result = CliRunner().invoke(
        app,
        [
            "scan",
            "--images",
            str(images_dir),
            "--source",
            "miharu",
            "--run-id",
            "ch03",
            "--data-dir",
            str(data_dir),
            "--ocr-mode",
            "sidecar",
        ],
    )

    assert result.exit_code == 0
    payload = json.loads((data_dir / "miharu" / "ch03" / "scan.json").read_text(encoding="utf-8"))
    assert "役立たず" in payload["candidates"]
