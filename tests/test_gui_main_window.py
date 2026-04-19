"""Tests for the main application window (Phase 4)."""
from __future__ import annotations

import sys

import pytest


def _pyside6_available() -> bool:
    try:
        import PySide6.QtWidgets  # noqa: F401
        return True
    except ImportError:
        return False


def _display_available() -> bool:
    """Check if a display is available for GUI tests."""
    if sys.platform == "win32":
        return True
    import os
    return bool(os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"))


pytestmark = pytest.mark.gui
skip_no_gui = pytest.mark.skipif(
    not _pyside6_available() or not _display_available(),
    reason="PySide6 or display not available",
)


@pytest.fixture()
def qapp():
    """Provide a QApplication for GUI tests."""
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    yield app


@skip_no_gui
class TestMainWindowCreation:
    """Verify the main window can be created and has expected structure."""

    def test_creates_without_error(self, qapp, tmp_path):
        from jp_anki_builder.gui.main_window import MainWindow
        window = MainWindow(data_dir=str(tmp_path))
        assert window is not None
        window.close()

    def test_has_three_tabs(self, qapp, tmp_path):
        from jp_anki_builder.gui.main_window import MainWindow
        window = MainWindow(data_dir=str(tmp_path))
        assert window._tabs.count() == 3
        assert window._tabs.tabText(0) == "Batch Processing"
        assert window._tabs.tabText(1) == "Real-Time Overlay"
        assert window._tabs.tabText(2) == "Settings"
        window.close()

    def test_window_title(self, qapp, tmp_path):
        from jp_anki_builder.gui.main_window import MainWindow
        window = MainWindow(data_dir=str(tmp_path))
        assert window.windowTitle() == "JP Anki Builder"
        window.close()

    def test_batch_tab_has_action_buttons(self, qapp, tmp_path):
        from jp_anki_builder.gui.main_window import MainWindow
        window = MainWindow(data_dir=str(tmp_path))
        assert window._scan_btn is not None
        assert window._build_btn is not None
        assert window._run_all_btn is not None
        assert window._clear_btn is not None
        window.close()

    def test_status_bar_shows_ready(self, qapp, tmp_path):
        from jp_anki_builder.gui.main_window import MainWindow
        window = MainWindow(data_dir=str(tmp_path))
        assert window._status_bar.currentMessage() == "Ready"
        window.close()


@skip_no_gui
class TestMainWindowPathDrop:
    """Verify path drop populates source fields."""

    def test_directory_drop_populates_fields(self, qapp, tmp_path):
        from jp_anki_builder.gui.main_window import MainWindow
        window = MainWindow(data_dir=str(tmp_path))
        # Simulate a directory drop
        source_dir = tmp_path / "manga" / "vol01"
        source_dir.mkdir(parents=True)
        window._on_path_dropped(str(source_dir))
        assert window._images_path == str(source_dir)
        assert window._source_field.text() != ""
        assert window._path_label.text() == str(source_dir)
        assert not window._path_label.isHidden()
        window.close()

    def test_file_drop_populates_fields(self, qapp, tmp_path):
        from jp_anki_builder.gui.main_window import MainWindow
        window = MainWindow(data_dir=str(tmp_path))
        video_file = tmp_path / "anime" / "episode01.mkv"
        video_file.parent.mkdir(parents=True)
        video_file.touch()
        window._on_path_dropped(str(video_file))
        assert window._source_field.text() == "anime"
        assert window._run_id_field.text() == "episode01"
        window.close()


@skip_no_gui
class TestMainWindowClear:
    """Verify the Clear button resets state."""

    def test_clear_resets_all_fields(self, qapp, tmp_path):
        from jp_anki_builder.gui.main_window import MainWindow
        window = MainWindow(data_dir=str(tmp_path))

        # Set up some state
        window._source_field.setText("test_source")
        window._run_id_field.setText("test_run")
        window._volume_field.setText("01")
        window._chapter_field.setText("05")
        window._images_path = "/some/path"
        window._path_label.setText("/some/path")
        window._path_label.show()
        window._log_view.append("some log text")

        # Click clear
        window._on_clear_clicked()

        assert window._source_field.text() == ""
        assert window._run_id_field.text() == ""
        assert window._volume_field.text() == ""
        assert window._chapter_field.text() == ""
        assert window._images_path == ""
        assert window._path_label.text() == ""
        assert not window._path_label.isVisible()
        assert window._log_view.toPlainText() == ""
        window.close()


@skip_no_gui
class TestMainWindowSetters:
    """Verify set_status and set_progress helpers."""

    def test_set_status(self, qapp, tmp_path):
        from jp_anki_builder.gui.main_window import MainWindow
        window = MainWindow(data_dir=str(tmp_path))
        window.set_status("Scanning...")
        assert window._status_bar.currentMessage() == "Scanning..."
        window.close()

    def test_set_progress(self, qapp, tmp_path):
        from jp_anki_builder.gui.main_window import MainWindow
        window = MainWindow(data_dir=str(tmp_path))
        window.set_progress(42)
        assert window._progress_bar.value() == 42
        window.close()

    def test_set_progress_clamps(self, qapp, tmp_path):
        from jp_anki_builder.gui.main_window import MainWindow
        window = MainWindow(data_dir=str(tmp_path))
        window.set_progress(150)
        assert window._progress_bar.value() == 100
        window.set_progress(-10)
        assert window._progress_bar.value() == 0
        window.close()
