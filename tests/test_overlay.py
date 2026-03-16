from __future__ import annotations

import sys

import pytest

from jp_anki_builder.lookup_service import LookupResult
from jp_anki_builder.realtime.overlay import (
    _CURSOR_OFFSET_X,
    _CURSOR_OFFSET_Y,
    _PYSIDE6_AVAILABLE,
    OverlayWidget,
    _apply_click_through,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _result(
    surface="食べる",
    dictionary_form="食べる",
    reading="たべる",
    meanings=None,
    part_of_speech="動詞",
    confidence=0.99,
    jlpt_level="N4",
    is_in_vocab_db=False,
) -> LookupResult:
    return LookupResult(
        surface=surface,
        dictionary_form=dictionary_form,
        reading=reading,
        meanings=meanings or ["to eat", "to consume"],
        part_of_speech=part_of_speech,
        confidence=confidence,
        jlpt_level=jlpt_level,
        is_in_vocab_db=is_in_vocab_db,
    )


# ---------------------------------------------------------------------------
# Module-level tests (no PySide6 required)
# ---------------------------------------------------------------------------

class TestModuleImport:
    def test_overlay_module_importable_without_pyside6(self):
        """The module must be importable even if PySide6 is absent."""
        import jp_anki_builder.realtime.overlay  # noqa: F401 — just checking no error

    def test_pyside6_available_flag_is_bool(self):
        assert isinstance(_PYSIDE6_AVAILABLE, bool)

    @pytest.mark.skipif(_PYSIDE6_AVAILABLE, reason="Only when PySide6 is absent")
    def test_stub_raises_import_error(self):
        with pytest.raises(ImportError, match="PySide6"):
            OverlayWidget()


class TestApplyClickThrough:
    def test_no_op_on_non_windows(self, monkeypatch):
        monkeypatch.setattr(sys, "platform", "linux")
        # Should not raise regardless of widget type.
        _apply_click_through(object())

    def test_no_op_on_darwin(self, monkeypatch):
        monkeypatch.setattr(sys, "platform", "darwin")
        _apply_click_through(object())


# ---------------------------------------------------------------------------
# GUI tests — skipped when PySide6 is not installed
# ---------------------------------------------------------------------------

@pytest.mark.skipif(not _PYSIDE6_AVAILABLE, reason="PySide6 not installed")
class TestOverlayWidgetFlags:
    @pytest.fixture(autouse=True)
    def qt_app(self):
        from PySide6.QtWidgets import QApplication
        app = QApplication.instance() or QApplication([])
        yield app

    def test_creates_without_error(self):
        widget = OverlayWidget()
        widget.deleteLater()

    def test_window_flags_always_on_top(self):
        from PySide6.QtCore import Qt
        widget = OverlayWidget()
        flags = widget.windowFlags()
        assert flags & Qt.WindowType.WindowStaysOnTopHint
        widget.deleteLater()

    def test_window_flags_frameless(self):
        from PySide6.QtCore import Qt
        widget = OverlayWidget()
        flags = widget.windowFlags()
        assert flags & Qt.WindowType.FramelessWindowHint
        widget.deleteLater()

    def test_window_flags_tool_no_taskbar(self):
        from PySide6.QtCore import Qt
        widget = OverlayWidget()
        flags = widget.windowFlags()
        assert flags & Qt.WindowType.Tool
        widget.deleteLater()

    def test_translucent_background_attribute(self):
        from PySide6.QtCore import Qt
        widget = OverlayWidget()
        assert widget.testAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        widget.deleteLater()


@pytest.mark.skipif(not _PYSIDE6_AVAILABLE, reason="PySide6 not installed")
class TestOverlayWidgetBehaviour:
    @pytest.fixture(autouse=True)
    def qt_app(self):
        from PySide6.QtWidgets import QApplication
        app = QApplication.instance() or QApplication([])
        yield app

    def test_show_results_makes_widget_visible(self):
        widget = OverlayWidget()
        widget.show_results([_result()], 100, 100)
        assert widget.isVisible()
        widget.deleteLater()

    def test_hide_results_hides_widget(self):
        widget = OverlayWidget()
        widget.show_results([_result()], 100, 100)
        widget.hide_results()
        assert not widget.isVisible()
        widget.deleteLater()

    def test_show_results_empty_list_hides_widget(self):
        widget = OverlayWidget()
        widget.show_results([], 100, 100)
        assert not widget.isVisible()
        widget.deleteLater()

    def test_show_results_populates_entries(self):
        widget = OverlayWidget()
        results = [_result("食べる"), _result("行く", reading="いく", jlpt_level="N5")]
        widget.show_results(results, 100, 100)
        # Two cards should have been added to the layout.
        assert widget._layout.count() == 2
        widget.deleteLater()

    def test_show_results_clears_previous_entries(self):
        widget = OverlayWidget()
        widget.show_results([_result(), _result("行く")], 100, 100)
        widget.show_results([_result()], 100, 100)
        assert widget._layout.count() == 1
        widget.deleteLater()


@pytest.mark.skipif(not _PYSIDE6_AVAILABLE, reason="PySide6 not installed")
class TestPositioning:
    @pytest.fixture(autouse=True)
    def qt_app(self):
        from PySide6.QtWidgets import QApplication
        app = QApplication.instance() or QApplication([])
        yield app

    def test_positioned_offset_from_cursor(self):
        widget = OverlayWidget()
        widget.show_results([_result()], 200, 300)
        # Without screen overflow the popup should be at cursor + offset.
        pos = widget.pos()
        assert pos.x() == 200 + _CURSOR_OFFSET_X
        assert pos.y() == 300 + _CURSOR_OFFSET_Y
        widget.deleteLater()

    def test_position_stays_on_screen(self):
        from PySide6.QtWidgets import QApplication
        widget = OverlayWidget()
        screen = QApplication.primaryScreen()
        if screen is None:
            pytest.skip("no screen available")
        geom = screen.geometry()
        # Place cursor at bottom-right corner — popup must clamp inside screen.
        widget.show_results([_result()], geom.right() - 5, geom.bottom() - 5)
        pos = widget.pos()
        assert pos.x() >= geom.left()
        assert pos.y() >= geom.top()
        assert pos.x() + widget.width() <= geom.right() + 1  # allow 1px rounding
        assert pos.y() + widget.height() <= geom.bottom() + 1
        widget.deleteLater()
