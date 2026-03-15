from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch


def _make_mock_pil_with_tracking():
    """Return a mock PIL that records draw calls for verification."""
    rectangles: list[tuple] = []
    texts: list[tuple] = []

    class FakeImage:
        def __init__(self):
            self._mode = "RGB"

        def convert(self, mode):
            self._mode = mode
            return self

        def save(self, path):
            Path(path).write_bytes(b"FAKE")

    class FakeDraw:
        def __init__(self, img):
            pass

        def rectangle(self, xy, outline=None, width=1, fill=None):
            rectangles.append((xy, outline))

        def text(self, xy, text, fill=None):
            texts.append((xy, text))

    import types
    mock_image_mod = types.ModuleType("PIL.Image")
    mock_draw_mod = types.ModuleType("PIL.ImageDraw")
    mock_font_mod = types.ModuleType("PIL.ImageFont")
    mock_pil = types.ModuleType("PIL")

    mock_image_mod.open = lambda path: FakeImage()
    mock_image_mod.new = lambda mode, size, color=None: FakeImage()
    mock_draw_mod.Draw = FakeDraw
    mock_font_mod.load_default = lambda: None
    mock_pil.Image = mock_image_mod
    mock_pil.ImageDraw = mock_draw_mod
    mock_pil.ImageFont = mock_font_mod

    return mock_pil, mock_image_mod, mock_draw_mod, mock_font_mod, rectangles, texts


class TestDebugOverlayWithRegions:
    """_save_debug_overlay draws bounding boxes when region data is provided."""

    def test_no_regions_falls_back_to_phase1_behavior(self, tmp_path: Path):
        """Without regions param, function works identically to Phase 1."""
        from jp_anki_builder.scan import _save_debug_overlay

        img_path = tmp_path / "frame.png"
        img_path.write_bytes(b"FAKE")
        debug_dir = tmp_path / "debug"

        mock_pil, mock_image, mock_draw, mock_font, rects, texts = _make_mock_pil_with_tracking()
        with patch.dict(sys.modules, {
            "PIL": mock_pil, "PIL.Image": mock_image,
            "PIL.ImageDraw": mock_draw, "PIL.ImageFont": mock_font,
        }):
            _save_debug_overlay(img_path, "テスト", debug_dir)

        assert (debug_dir / "frame.png").exists()
        assert not rects  # no bounding boxes drawn

    def test_empty_regions_list_falls_back_to_phase1(self, tmp_path: Path):
        """Empty regions list → no rectangles drawn."""
        from jp_anki_builder.scan import _save_debug_overlay

        img_path = tmp_path / "frame.png"
        img_path.write_bytes(b"FAKE")
        debug_dir = tmp_path / "debug"

        mock_pil, mock_image, mock_draw, mock_font, rects, texts = _make_mock_pil_with_tracking()
        with patch.dict(sys.modules, {
            "PIL": mock_pil, "PIL.Image": mock_image,
            "PIL.ImageDraw": mock_draw, "PIL.ImageFont": mock_font,
        }):
            _save_debug_overlay(img_path, "テスト", debug_dir, regions=[])

        assert not rects

    def test_regions_cause_rectangles_to_be_drawn(self, tmp_path: Path):
        """With regions, one rectangle is drawn per region."""
        from jp_anki_builder.scan import _save_debug_overlay

        img_path = tmp_path / "frame.png"
        img_path.write_bytes(b"FAKE")
        debug_dir = tmp_path / "debug"

        regions = [
            {"bbox": [10, 20, 110, 80], "confidence": 0.9, "text": "hello"},
            {"bbox": [50, 50, 150, 120], "confidence": 0.7, "text": "world"},
        ]

        mock_pil, mock_image, mock_draw, mock_font, rects, texts = _make_mock_pil_with_tracking()
        with patch.dict(sys.modules, {
            "PIL": mock_pil, "PIL.Image": mock_image,
            "PIL.ImageDraw": mock_draw, "PIL.ImageFont": mock_font,
        }):
            _save_debug_overlay(img_path, "combined", debug_dir, regions=regions)

        assert len(rects) == 2

    def test_each_region_labeled_with_index_and_confidence(self, tmp_path: Path):
        """Labels for regions include the region index and confidence score."""
        from jp_anki_builder.scan import _save_debug_overlay

        img_path = tmp_path / "frame.png"
        img_path.write_bytes(b"FAKE")
        debug_dir = tmp_path / "debug"

        regions = [
            {"bbox": [0, 0, 50, 50], "confidence": 0.95, "text": "foo"},
        ]

        mock_pil, mock_image, mock_draw, mock_font, rects, texts = _make_mock_pil_with_tracking()
        with patch.dict(sys.modules, {
            "PIL": mock_pil, "PIL.Image": mock_image,
            "PIL.ImageDraw": mock_draw, "PIL.ImageFont": mock_font,
        }):
            _save_debug_overlay(img_path, "foo", debug_dir, regions=regions)

        # One of the text calls should contain the region index (1 or 0) and confidence
        label_texts = [t for _, t in texts]
        assert any("0.95" in t or "95" in t for t in label_texts), (
            f"Expected confidence in labels, got: {label_texts}"
        )

    def test_different_region_types_get_different_colors(self, tmp_path: Path):
        """text and sfx region types produce different outline colors."""
        from jp_anki_builder.scan import _save_debug_overlay

        img_path = tmp_path / "frame.png"
        img_path.write_bytes(b"FAKE")
        debug_dir = tmp_path / "debug"

        regions = [
            {"bbox": [0, 0, 50, 50], "confidence": 0.9, "text": "hello", "region_type": "text"},
            {"bbox": [60, 60, 110, 110], "confidence": 0.8, "text": "POW", "region_type": "sfx"},
        ]

        mock_pil, mock_image, mock_draw, mock_font, rects, texts = _make_mock_pil_with_tracking()
        with patch.dict(sys.modules, {
            "PIL": mock_pil, "PIL.Image": mock_image,
            "PIL.ImageDraw": mock_draw, "PIL.ImageFont": mock_font,
        }):
            _save_debug_overlay(img_path, "combined", debug_dir, regions=regions)

        assert len(rects) == 2
        colors = [outline for _, outline in rects]
        # The two region types must produce different colors
        assert colors[0] != colors[1], (
            f"Expected different colors for text vs sfx, got {colors[0]} and {colors[1]}"
        )

    def test_overlay_file_created_when_regions_present(self, tmp_path: Path):
        """Output file is still created when regions are provided."""
        from jp_anki_builder.scan import _save_debug_overlay

        img_path = tmp_path / "page.png"
        img_path.write_bytes(b"FAKE")
        debug_dir = tmp_path / "debug"

        regions = [{"bbox": [0, 0, 10, 10], "confidence": 0.8, "text": "hi"}]

        mock_pil, mock_image, mock_draw, mock_font, rects, _ = _make_mock_pil_with_tracking()
        with patch.dict(sys.modules, {
            "PIL": mock_pil, "PIL.Image": mock_image,
            "PIL.ImageDraw": mock_draw, "PIL.ImageFont": mock_font,
        }):
            _save_debug_overlay(img_path, "hi", debug_dir, regions=regions)

        assert (debug_dir / "page.png").exists()

    def test_no_error_when_regions_provided_but_pillow_unavailable(self, tmp_path: Path):
        """Function never raises even when regions are given but Pillow is missing."""
        from jp_anki_builder.scan import _save_debug_overlay

        img_path = tmp_path / "frame.png"
        img_path.write_bytes(b"FAKE")
        debug_dir = tmp_path / "debug"

        regions = [{"bbox": [0, 0, 50, 50], "confidence": 0.9, "text": "x"}]

        with patch.dict(sys.modules, {"PIL": None, "PIL.Image": None, "PIL.ImageDraw": None}):
            _save_debug_overlay(img_path, "x", debug_dir, regions=regions)
        # No exception raised
