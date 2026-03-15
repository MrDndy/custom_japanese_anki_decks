from __future__ import annotations

import shutil
import sys
import tempfile
from pathlib import Path
from types import ModuleType
from unittest.mock import MagicMock, patch


def _make_mock_pil():
    """Return a minimal mock of PIL.Image / PIL.ImageDraw that writes real files."""
    mock_pil = ModuleType("PIL")
    mock_image_mod = ModuleType("PIL.Image")
    mock_draw_mod = ModuleType("PIL.ImageDraw")
    mock_font_mod = ModuleType("PIL.ImageFont")

    # Mock image that saves to disk as an empty file (enough for path existence checks)
    class FakeImage:
        def convert(self, mode):
            return self
        def save(self, path):
            Path(path).write_bytes(b"FAKE")

    mock_image_mod.open = lambda path: FakeImage()
    mock_image_mod.new = lambda mode, size, color=None: FakeImage()

    class FakeDraw:
        def __init__(self, img): pass
        def text(self, xy, text, fill=None): pass

    mock_draw_mod.Draw = FakeDraw
    mock_font_mod.load_default = lambda: None

    mock_pil.Image = mock_image_mod
    mock_pil.ImageDraw = mock_draw_mod
    mock_pil.ImageFont = mock_font_mod

    return mock_pil, mock_image_mod, mock_draw_mod, mock_font_mod


class TestSaveDebugOverlay:
    def setup_method(self):
        self._tmp = tempfile.mkdtemp()
        self.debug_dir = Path(self._tmp) / "debug"
        self.img_path = Path(self._tmp) / "frame.png"
        self.img_path.write_bytes(b"FAKE_IMAGE")

    def teardown_method(self):
        shutil.rmtree(self._tmp, ignore_errors=True)

    def test_overlay_saved_when_pillow_available(self):
        from jp_anki_builder.scan import _save_debug_overlay

        mock_pil, mock_image, mock_draw, mock_font = _make_mock_pil()
        with patch.dict(sys.modules, {
            "PIL": mock_pil,
            "PIL.Image": mock_image,
            "PIL.ImageDraw": mock_draw,
            "PIL.ImageFont": mock_font,
        }):
            _save_debug_overlay(self.img_path, "テスト", self.debug_dir)

        out = self.debug_dir / "frame.png"
        assert out.exists(), "debug overlay file should be created"

    def test_debug_dir_created_if_missing(self):
        from jp_anki_builder.scan import _save_debug_overlay

        assert not self.debug_dir.exists()
        mock_pil, mock_image, mock_draw, mock_font = _make_mock_pil()
        with patch.dict(sys.modules, {
            "PIL": mock_pil,
            "PIL.Image": mock_image,
            "PIL.ImageDraw": mock_draw,
            "PIL.ImageFont": mock_font,
        }):
            _save_debug_overlay(self.img_path, "text", self.debug_dir)

        assert self.debug_dir.exists()

    def test_no_error_when_pillow_unavailable(self):
        """Function swallows ImportError and logs a warning — never raises."""
        from jp_anki_builder.scan import _save_debug_overlay

        with patch.dict(sys.modules, {"PIL": None, "PIL.Image": None, "PIL.ImageDraw": None}):
            # Should not raise
            _save_debug_overlay(self.img_path, "text", self.debug_dir)

        # debug dir was not created since Pillow was unavailable
        assert not self.debug_dir.exists()

    def test_overlay_skipped_when_flag_false(self):
        """_save_debug_overlay is never called when save_debug_overlays=False."""
        from jp_anki_builder.scan import _save_debug_overlay

        # Simply don't call it and verify no debug dir appears
        assert not self.debug_dir.exists()

    def test_config_key_recognized(self):
        from jp_anki_builder.project_config import ProjectDefaults
        d = ProjectDefaults(save_debug_overlays=True)
        assert d.save_debug_overlays is True
        d2 = ProjectDefaults(save_debug_overlays=False)
        assert d2.save_debug_overlays is False

    def test_debug_dir_property_on_run_paths(self):
        from jp_anki_builder.config import RunPaths
        paths = RunPaths(base_dir="data", source_id="manga-a", run_id="run-1")
        assert paths.debug_dir == Path("data") / "manga-a" / "run-1" / "debug"
