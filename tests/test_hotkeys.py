from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from jp_anki_builder.realtime.hotkeys import (
    DEFAULT_HOTKEY_ADD_WORD,
    DEFAULT_HOTKEY_EXPORT,
    DEFAULT_HOTKEY_SCAN,
    HotkeyManager,
    _PYNPUT_AVAILABLE,
    _canonicalize_key,
    _parse_hotkey,
)


# ---------------------------------------------------------------------------
# _parse_hotkey — pure function, no pynput required
# ---------------------------------------------------------------------------

class TestParseHotkey:
    def test_two_modifier_combo(self):
        result = _parse_hotkey("ctrl+shift")
        assert result == frozenset({"ctrl", "shift"})

    def test_three_key_combo(self):
        result = _parse_hotkey("ctrl+shift+a")
        assert result == frozenset({"ctrl", "shift", "a"})

    def test_case_insensitive(self):
        assert _parse_hotkey("Ctrl+Shift+A") == _parse_hotkey("ctrl+shift+a")

    def test_strips_whitespace(self):
        assert _parse_hotkey("ctrl + shift") == frozenset({"ctrl", "shift"})

    def test_single_key(self):
        assert _parse_hotkey("f12") == frozenset({"f12"})

    def test_returns_frozenset(self):
        assert isinstance(_parse_hotkey("ctrl+shift"), frozenset)

    def test_export_default(self):
        result = _parse_hotkey(DEFAULT_HOTKEY_EXPORT)
        assert "shift" in result
        assert "e" in result

    def test_add_word_default(self):
        result = _parse_hotkey(DEFAULT_HOTKEY_ADD_WORD)
        assert "shift" in result
        assert "q" in result

    def test_scan_default(self):
        result = _parse_hotkey(DEFAULT_HOTKEY_SCAN)
        assert "shift" in result


# ---------------------------------------------------------------------------
# HotkeyManager — registration (no pynput required)
# ---------------------------------------------------------------------------

class TestRegistration:
    def test_register_stores_callback(self):
        mgr = HotkeyManager()
        cb = MagicMock()
        mgr.register("ctrl+shift+a", cb)
        assert "ctrl+shift+a" in mgr._callbacks
        assert mgr._callbacks["ctrl+shift+a"] is cb

    def test_register_without_release(self):
        mgr = HotkeyManager()
        mgr.register("ctrl+shift", MagicMock())
        assert "ctrl+shift" not in mgr._release_callbacks

    def test_register_with_release(self):
        mgr = HotkeyManager()
        press_cb = MagicMock()
        release_cb = MagicMock()
        mgr.register("ctrl+shift", press_cb, on_release=release_cb)
        assert mgr._release_callbacks["ctrl+shift"] is release_cb

    def test_register_multiple_hotkeys(self):
        mgr = HotkeyManager()
        mgr.register("ctrl+shift", MagicMock())
        mgr.register("ctrl+shift+a", MagicMock())
        mgr.register("ctrl+shift+e", MagicMock())
        assert len(mgr._callbacks) == 3

    def test_register_overwrites_existing(self):
        mgr = HotkeyManager()
        cb1 = MagicMock()
        cb2 = MagicMock()
        mgr.register("ctrl+a", cb1)
        mgr.register("ctrl+a", cb2)
        assert mgr._callbacks["ctrl+a"] is cb2


# ---------------------------------------------------------------------------
# HotkeyManager — simulated press/release (no real pynput listener needed)
# ---------------------------------------------------------------------------

class TestPressReleaseSim:
    """Directly call _on_press / _on_release with mock key objects."""

    def _make_key(self, canonical_name: str):
        """Return a mock object that _canonicalize_key will map to canonical_name."""
        from unittest.mock import patch as _patch
        import jp_anki_builder.realtime.hotkeys as _mod

        # We'll patch _canonicalize_key at the module level to control what it returns.
        return canonical_name  # used as a sentinel; patching done per-test

    def _sim_press(self, mgr: HotkeyManager, *canonical_names: str) -> None:
        """Simulate pressing keys by directly injecting into _pressed_keys and calling _on_press."""
        import jp_anki_builder.realtime.hotkeys as _mod

        for name in canonical_names:
            mock_key = MagicMock()
            with patch.object(_mod, "_canonicalize_key", return_value=name):
                mgr._on_press(mock_key)

    def _sim_release(self, mgr: HotkeyManager, *canonical_names: str) -> None:
        import jp_anki_builder.realtime.hotkeys as _mod

        for name in canonical_names:
            mock_key = MagicMock()
            with patch.object(_mod, "_canonicalize_key", return_value=name):
                mgr._on_release(mock_key)

    def test_callback_fires_when_combo_pressed(self):
        mgr = HotkeyManager()
        cb = MagicMock()
        mgr.register("ctrl+shift", cb)
        self._sim_press(mgr, "ctrl", "shift")
        cb.assert_called_once()

    def test_callback_fires_only_once_while_held(self):
        mgr = HotkeyManager()
        cb = MagicMock()
        mgr.register("ctrl+shift", cb)
        self._sim_press(mgr, "ctrl", "shift")
        self._sim_press(mgr, "ctrl")  # already held — no re-fire
        cb.assert_called_once()

    def test_partial_combo_does_not_fire(self):
        mgr = HotkeyManager()
        cb = MagicMock()
        mgr.register("ctrl+shift+a", cb)
        self._sim_press(mgr, "ctrl", "shift")  # 'a' not pressed
        cb.assert_not_called()

    def test_release_callback_fires_on_key_release(self):
        mgr = HotkeyManager()
        press_cb = MagicMock()
        release_cb = MagicMock()
        mgr.register("ctrl+shift", press_cb, on_release=release_cb)
        self._sim_press(mgr, "ctrl", "shift")
        self._sim_release(mgr, "shift")
        release_cb.assert_called_once()

    def test_release_callback_not_fired_before_activation(self):
        mgr = HotkeyManager()
        release_cb = MagicMock()
        mgr.register("ctrl+shift", MagicMock(), on_release=release_cb)
        # Release without ever pressing the full combo
        self._sim_release(mgr, "shift")
        release_cb.assert_not_called()

    def test_combo_reactivates_after_release(self):
        mgr = HotkeyManager()
        cb = MagicMock()
        mgr.register("ctrl+shift", cb)
        self._sim_press(mgr, "ctrl", "shift")
        self._sim_release(mgr, "shift")
        # Press again — should fire a second time
        self._sim_press(mgr, "shift")
        assert cb.call_count == 2

    def test_none_key_ignored(self):
        """_canonicalize_key returning None should not crash."""
        import jp_anki_builder.realtime.hotkeys as _mod

        mgr = HotkeyManager()
        cb = MagicMock()
        mgr.register("ctrl+shift", cb)
        with patch.object(_mod, "_canonicalize_key", return_value=None):
            mgr._on_press(MagicMock())
        cb.assert_not_called()

    def test_callback_exception_does_not_crash_manager(self):
        mgr = HotkeyManager()
        mgr.register("ctrl+a", MagicMock(side_effect=RuntimeError("boom")))
        # Should not raise
        self._sim_press(mgr, "ctrl", "a")


# ---------------------------------------------------------------------------
# _canonicalize_key — shifted number recovery
# ---------------------------------------------------------------------------

@pytest.mark.skipif(not _PYNPUT_AVAILABLE, reason="pynput not installed")
class TestCanonicalizeShiftedNumbers:
    """Shift+1 produces '!' on US keyboards — we must map it back to '1'."""

    def _make_keycode(self, char: str):
        from pynput.keyboard import KeyCode
        return KeyCode.from_char(char)

    def test_exclamation_maps_to_1(self):
        assert _canonicalize_key(self._make_keycode("!")) == "1"

    def test_at_maps_to_2(self):
        assert _canonicalize_key(self._make_keycode("@")) == "2"

    def test_hash_maps_to_3(self):
        assert _canonicalize_key(self._make_keycode("#")) == "3"

    def test_plain_number_unchanged(self):
        assert _canonicalize_key(self._make_keycode("5")) == "5"

    def test_plain_letter_unchanged(self):
        assert _canonicalize_key(self._make_keycode("q")) == "q"


class TestNumberedWordSelection:
    """Shift+N hotkeys fire indexed callbacks via the press simulation."""

    def _sim_press(self, mgr: HotkeyManager, *canonical_names: str) -> None:
        import jp_anki_builder.realtime.hotkeys as _mod
        for name in canonical_names:
            mock_key = MagicMock()
            with patch.object(_mod, "_canonicalize_key", return_value=name):
                mgr._on_press(mock_key)

    def _sim_release(self, mgr: HotkeyManager, *canonical_names: str) -> None:
        import jp_anki_builder.realtime.hotkeys as _mod
        for name in canonical_names:
            mock_key = MagicMock()
            with patch.object(_mod, "_canonicalize_key", return_value=name):
                mgr._on_release(mock_key)

    def test_shift_plus_1_fires_indexed_callback(self):
        mgr = HotkeyManager()
        called_with = []
        mgr.register("shift+1", callback=lambda: called_with.append(0))
        self._sim_press(mgr, "shift", "1")
        assert called_with == [0]

    def test_shift_plus_3_fires_correct_index(self):
        mgr = HotkeyManager()
        results = []
        for n in range(1, 4):
            idx = n - 1
            mgr.register(f"shift+{n}", callback=lambda i=idx: results.append(i))
        self._sim_press(mgr, "shift", "3")
        assert results == [2]

    def test_number_without_shift_does_not_fire(self):
        mgr = HotkeyManager()
        called = []
        mgr.register("shift+1", callback=lambda: called.append(True))
        self._sim_press(mgr, "1")
        assert called == []


# ---------------------------------------------------------------------------
# Default hotkey values
# ---------------------------------------------------------------------------

class TestDefaults:
    def test_scan_default_is_string(self):
        assert isinstance(DEFAULT_HOTKEY_SCAN, str)

    def test_add_word_default_is_string(self):
        assert isinstance(DEFAULT_HOTKEY_ADD_WORD, str)

    def test_export_default_is_string(self):
        assert isinstance(DEFAULT_HOTKEY_EXPORT, str)


# ---------------------------------------------------------------------------
# project_config hotkey keys
# ---------------------------------------------------------------------------

class TestProjectConfigHotkeyKeys:
    def test_hotkey_scan_in_project_defaults(self):
        from jp_anki_builder.project_config import ProjectDefaults
        pd = ProjectDefaults()
        assert hasattr(pd, "hotkey_scan")
        assert pd.hotkey_scan is None

    def test_hotkey_add_word_in_project_defaults(self):
        from jp_anki_builder.project_config import ProjectDefaults
        pd = ProjectDefaults()
        assert hasattr(pd, "hotkey_add_word")

    def test_hotkey_export_in_project_defaults(self):
        from jp_anki_builder.project_config import ProjectDefaults
        pd = ProjectDefaults()
        assert hasattr(pd, "hotkey_export")

    def test_hotkey_keys_loadable_from_config(self, tmp_path):
        import json
        from jp_anki_builder.project_config import load_project_config

        cfg = {"hotkey_scan": "ctrl+alt", "hotkey_add_word": "ctrl+alt+a"}
        (tmp_path / ".jp-anki.json").write_text(json.dumps(cfg))
        defaults = load_project_config(data_dir=str(tmp_path))
        assert defaults.hotkey_scan == "ctrl+alt"
        assert defaults.hotkey_add_word == "ctrl+alt+a"


# ---------------------------------------------------------------------------
# Lifecycle — skipped when pynput absent
# ---------------------------------------------------------------------------

@pytest.mark.skipif(not _PYNPUT_AVAILABLE, reason="pynput not installed")
class TestLifecycle:
    def test_start_sets_running(self):
        mgr = HotkeyManager()
        mgr.start()
        assert mgr.running is True
        mgr.stop()

    def test_stop_clears_running(self):
        mgr = HotkeyManager()
        mgr.start()
        mgr.stop()
        assert mgr.running is False

    def test_double_start_is_idempotent(self):
        mgr = HotkeyManager()
        mgr.start()
        mgr.start()  # should not raise or create second listener
        mgr.stop()

    def test_stop_without_start_is_noop(self):
        mgr = HotkeyManager()
        mgr.stop()  # should not raise


@pytest.mark.skipif(_PYNPUT_AVAILABLE, reason="Only when pynput absent")
class TestLifecycleNoPynput:
    def test_start_raises_runtime_error(self):
        mgr = HotkeyManager()
        with pytest.raises(RuntimeError, match="pynput"):
            mgr.start()
