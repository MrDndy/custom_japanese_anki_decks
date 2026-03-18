"""Integration tests for the Phase 3 real-time pipeline.

These tests exercise multiple Phase 3 components end-to-end without any
mocking of the core logic (only hardware/GUI is mocked where necessary).

Test scenarios:
- LookupService → SessionBuffer → export_deck (full pipeline without real hardware)
- AnkiConnect config keys round-trip through project_config
- OverlayApp / BufferPanel stub paths when PySide6 is absent
"""
from __future__ import annotations

import json
import zipfile
from pathlib import Path

import pytest

from jp_anki_builder.lookup_service import LookupResult, LookupService
from jp_anki_builder.realtime.session import SessionBuffer


# ---------------------------------------------------------------------------
# Helper: build a LookupResult as the real LookupService would
# ---------------------------------------------------------------------------

def _make_result(
    surface: str = "食べる",
    dictionary_form: str = "食べる",
    reading: str = "たべる",
    meanings: list[str] | None = None,
    jlpt_level: str = "N4",
) -> LookupResult:
    return LookupResult(
        surface=surface,
        dictionary_form=dictionary_form,
        reading=reading,
        meanings=meanings or ["to eat", "to consume"],
        part_of_speech="動詞",
        confidence=0.99,
        jlpt_level=jlpt_level,
        is_in_vocab_db=False,
    )


# ---------------------------------------------------------------------------
# LookupService → SessionBuffer → export_deck
# ---------------------------------------------------------------------------

class TestLookupToExportPipeline:
    """Full pipeline: tokenise Japanese text, buffer the words, export deck."""

    def test_lookup_then_add_then_export(self, tmp_path):
        """Words returned from LookupService can be added to SessionBuffer and exported."""
        svc = LookupService(data_dir=str(tmp_path), online_dict="off")
        response = svc.lookup("食べる")

        buf = SessionBuffer(data_dir=str(tmp_path))
        added_count = 0
        for word in response.words:
            if buf.add_word(word, response.raw_text):
                added_count += 1

        assert added_count >= 1, "At least one word should have been buffered"

        deck_path = buf.export_deck("integration_test")
        assert deck_path.exists()
        assert zipfile.is_zipfile(deck_path)

    def test_sentence_lookup_then_buffer_then_export(self, tmp_path):
        """Full sentence → lookup → buffer → export should produce a valid .apkg."""
        svc = LookupService(data_dir=str(tmp_path), online_dict="off")
        response = svc.lookup("昨日は友達と食べに行った")

        # Particles must have been filtered — only content words buffered.
        buf = SessionBuffer(data_dir=str(tmp_path))
        for word in response.words:
            buf.add_word(word, response.raw_text)

        assert len(buf) >= 1

        deck_path = buf.export_deck("sentence_test")
        assert deck_path.exists()
        assert zipfile.is_zipfile(deck_path)

    def test_dedup_across_multiple_lookups(self, tmp_path):
        """The same word found in two separate OCR frames is only buffered once."""
        svc = LookupService(data_dir=str(tmp_path), online_dict="off")
        buf = SessionBuffer(data_dir=str(tmp_path))

        resp1 = svc.lookup("食べる")
        for word in resp1.words:
            buf.add_word(word, resp1.raw_text)
        size_after_first = len(buf)

        resp2 = svc.lookup("食べる")  # same text → same words
        added_second_time = sum(
            1 for word in resp2.words if buf.add_word(word, resp2.raw_text)
        )

        assert added_second_time == 0, "No new words should be added from duplicate text"
        assert len(buf) == size_after_first

    def test_context_manager_lookup_then_buffer(self, tmp_path):
        """LookupService used as a context manager integrates with SessionBuffer."""
        buf = SessionBuffer(data_dir=str(tmp_path))
        with LookupService(data_dir=str(tmp_path)) as svc:
            response = svc.lookup("行く")
            for word in response.words:
                buf.add_word(word, response.raw_text)

        assert len(buf) >= 1


# ---------------------------------------------------------------------------
# AnkiConnect config keys in project_config
# ---------------------------------------------------------------------------

class TestAnkiConnectConfig:
    def test_ankiconnect_enabled_defaults_none(self):
        from jp_anki_builder.project_config import ProjectDefaults
        pd = ProjectDefaults()
        assert hasattr(pd, "ankiconnect_enabled")
        assert pd.ankiconnect_enabled is None

    def test_ankiconnect_port_defaults_none(self):
        from jp_anki_builder.project_config import ProjectDefaults
        pd = ProjectDefaults()
        assert hasattr(pd, "ankiconnect_port")
        assert pd.ankiconnect_port is None

    def test_ankiconnect_enabled_set_via_set_config(self, tmp_path):
        from jp_anki_builder.project_config import load_project_config, set_config
        set_config("ankiconnect_enabled", "true", data_dir=str(tmp_path))
        cfg = load_project_config(data_dir=str(tmp_path))
        assert cfg.ankiconnect_enabled is True

    def test_ankiconnect_enabled_false_via_set_config(self, tmp_path):
        from jp_anki_builder.project_config import load_project_config, set_config
        set_config("ankiconnect_enabled", "false", data_dir=str(tmp_path))
        cfg = load_project_config(data_dir=str(tmp_path))
        assert cfg.ankiconnect_enabled is False

    def test_ankiconnect_port_set_via_set_config(self, tmp_path):
        from jp_anki_builder.project_config import load_project_config, set_config
        set_config("ankiconnect_port", "9999", data_dir=str(tmp_path))
        cfg = load_project_config(data_dir=str(tmp_path))
        assert cfg.ankiconnect_port == 9999

    def test_ankiconnect_port_invalid_value_raises(self, tmp_path):
        from jp_anki_builder.project_config import set_config
        with pytest.raises(ValueError, match="integer"):
            set_config("ankiconnect_port", "notanint", data_dir=str(tmp_path))

    def test_ankiconnect_keys_in_valid_keys(self):
        from jp_anki_builder.project_config import VALID_KEYS
        assert "ankiconnect_enabled" in VALID_KEYS
        assert "ankiconnect_port" in VALID_KEYS

    def test_ankiconnect_config_round_trip_json(self, tmp_path):
        """Config written to disk and reloaded preserves ankiconnect settings."""
        cfg_path = tmp_path / ".jp-anki.json"
        cfg_path.write_text(json.dumps({
            "ankiconnect_enabled": True,
            "ankiconnect_port": 8765,
        }))
        from jp_anki_builder.project_config import load_project_config
        loaded = load_project_config(data_dir=str(tmp_path))
        assert loaded.ankiconnect_enabled is True
        assert loaded.ankiconnect_port == 8765


# ---------------------------------------------------------------------------
# OverlayApp stub behaviour (no PySide6)
# ---------------------------------------------------------------------------

class TestOverlayAppStub:
    from jp_anki_builder.realtime.app import _PYSIDE6_AVAILABLE as _av

    def test_module_importable(self):
        import jp_anki_builder.realtime.app  # noqa: F401

    def test_pyside6_available_flag_is_bool(self):
        from jp_anki_builder.realtime.app import _PYSIDE6_AVAILABLE
        assert isinstance(_PYSIDE6_AVAILABLE, bool)

    @pytest.mark.skipif(
        _av,
        reason="Only tests the stub path when PySide6 is absent",
    )
    def test_stub_raises_import_error_on_init(self):
        from jp_anki_builder.realtime.app import OverlayApp
        with pytest.raises(ImportError, match="PySide6"):
            OverlayApp()

    @pytest.mark.skipif(
        _av,
        reason="Only tests the stub path when PySide6 is absent",
    )
    def test_stub_run_raises_import_error(self):
        from jp_anki_builder.realtime.app import OverlayApp
        stub = object.__new__(OverlayApp)
        with pytest.raises(ImportError):
            stub.run()


# ---------------------------------------------------------------------------
# BufferPanel stub behaviour (no PySide6)
# ---------------------------------------------------------------------------

class TestBufferPanelStub:
    from jp_anki_builder.realtime.buffer_panel import _PYSIDE6_AVAILABLE as _av

    def test_module_importable(self):
        import jp_anki_builder.realtime.buffer_panel  # noqa: F401

    def test_pyside6_available_flag_is_bool(self):
        from jp_anki_builder.realtime.buffer_panel import _PYSIDE6_AVAILABLE
        assert isinstance(_PYSIDE6_AVAILABLE, bool)

    @pytest.mark.skipif(
        _av,
        reason="Only tests the stub path when PySide6 is absent",
    )
    def test_stub_raises_import_error_on_init(self):
        from jp_anki_builder.realtime.buffer_panel import BufferPanel
        with pytest.raises(ImportError, match="PySide6"):
            BufferPanel()

    @pytest.mark.skipif(
        _av,
        reason="Only tests the stub path when PySide6 is absent",
    )
    def test_stub_update_words_raises_import_error(self):
        from jp_anki_builder.realtime.buffer_panel import BufferPanel
        stub = object.__new__(BufferPanel)
        with pytest.raises(ImportError):
            stub.update_words([])


# ---------------------------------------------------------------------------
# CLI overlay command registered
# ---------------------------------------------------------------------------

class TestOverlayCli:
    def test_overlay_command_registered_in_cli(self):
        """jp-anki-build overlay should appear in the CLI app."""
        from typer.testing import CliRunner
        from jp_anki_builder.cli import app

        runner = CliRunner()
        result = runner.invoke(app, ["--help"])
        assert result.exit_code == 0
        assert "overlay" in result.output
