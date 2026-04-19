from __future__ import annotations

import logging
import threading
from collections.abc import Callable

logger = logging.getLogger(__name__)

# Checked at import time; used by tests and the stub path.
_PYNPUT_AVAILABLE = False
try:
    import pynput  # noqa: F401
    _PYNPUT_AVAILABLE = True
except ImportError:
    pass

# Default hotkey strings — callers can override via project_config.
DEFAULT_HOTKEY_SCAN = "shift"
DEFAULT_HOTKEY_ADD_WORD = "shift+q"
DEFAULT_HOTKEY_EXPORT = "shift+e"

# Modifier names that should be normalised from their left/right variants.
_MODIFIER_PREFIXES = ("ctrl", "shift", "alt", "cmd")


def _parse_hotkey(hotkey_str: str) -> frozenset[str]:
    """Parse a ``+``-separated hotkey string into a frozenset of canonical key names.

    Examples::

        _parse_hotkey("ctrl+shift")    → frozenset({"ctrl", "shift"})
        _parse_hotkey("ctrl+shift+a")  → frozenset({"ctrl", "shift", "a"})
        _parse_hotkey("Ctrl+Shift+A")  → frozenset({"ctrl", "shift", "a"})
    """
    parts = [p.strip().lower() for p in hotkey_str.split("+") if p.strip()]
    return frozenset(parts)


def _canonicalize_key(key) -> str | None:
    """Return a canonical key name string for a pynput *key* object.

    Modifier variants (ctrl_l / ctrl_r → ``"ctrl"``, shift_l / shift_r →
    ``"shift"``, etc.) are collapsed so that the held-key set can be compared
    directly with the output of :func:`_parse_hotkey`.

    Returns *None* for keys that cannot be represented (e.g. media keys).
    """
    try:
        from pynput.keyboard import Key, KeyCode
    except ImportError:
        return None

    if isinstance(key, Key):
        name = key.name  # e.g. "ctrl_l", "shift", "alt_r"
        for prefix in _MODIFIER_PREFIXES:
            if name.startswith(prefix):
                return prefix
        return name

    if isinstance(key, KeyCode):
        # On Windows, Shift changes number keys to symbols (1→!, 2→@, etc.)
        # Use the virtual key code to recover the unshifted character.
        _SHIFTED_NUMBERS = {"!": "1", "@": "2", "#": "3", "$": "4", "%": "5",
                            "^": "6", "&": "7", "*": "8", "(": "9"}
        if key.char is not None:
            ch = key.char.lower()
            return _SHIFTED_NUMBERS.get(ch, ch)
        # Fallback: check vk for number keys (0x30–0x39)
        vk = getattr(key, "vk", None)
        if vk is not None and 0x30 <= vk <= 0x39:
            return str(vk - 0x30)

    return None


class HotkeyManager:
    """Registers global hotkeys for scan-hold and add-word actions.

    Uses ``pynput.keyboard.Listener`` so hotkeys work even when the
    application window is not focused.

    Two registration modes:
    - **Press-only** (``on_release=None``): *callback* fires once when all
      keys in the combo are pressed simultaneously.
    - **Hold** (``on_release`` provided): *callback* fires on press of the
      full combo; *on_release* fires when any key in the combo is released
      while the combo was active.

    Example::

        mgr = HotkeyManager()
        mgr.register("ctrl+shift", start_scanning, on_release=stop_scanning)
        mgr.register("ctrl+shift+a", add_word)
        mgr.register("ctrl+shift+e", export_session)
        mgr.start()
        # ... app runs ...
        mgr.stop()
    """

    def __init__(self) -> None:
        self._callbacks: dict[str, Callable] = {}
        self._release_callbacks: dict[str, Callable] = {}
        self._listener = None
        self._pressed_keys: set[str] = set()
        self._active_combos: set[str] = set()
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def register(
        self,
        hotkey: str,
        callback: Callable,
        on_release: Callable | None = None,
    ) -> None:
        """Register *hotkey* combo with *callback*.

        *hotkey* is a ``+``-separated string such as ``"ctrl+shift+a"``.
        *callback* is called once when all keys in the combo are pressed.
        *on_release* (optional) is called when any key in the combo is
        released after the combo became active.
        """
        self._callbacks[hotkey] = callback
        if on_release is not None:
            self._release_callbacks[hotkey] = on_release

    def start(self) -> None:
        """Start listening for global hotkeys in a background thread."""
        if not _PYNPUT_AVAILABLE:
            raise RuntimeError(
                "pynput is not installed. "
                "Install with: pip install pynput"
            )
        if self._listener is not None:
            return  # already running

        from pynput.keyboard import Listener

        self._listener = Listener(
            on_press=self._on_press,
            on_release=self._on_release,
        )
        self._listener.start()
        logger.debug("hotkey listener started")

    def stop(self) -> None:
        """Stop listening and clean up."""
        if self._listener is not None:
            self._listener.stop()
            self._listener = None
            logger.debug("hotkey listener stopped")
        with self._lock:
            self._pressed_keys.clear()
            self._active_combos.clear()

    @property
    def running(self) -> bool:
        return self._listener is not None and self._listener.running

    # ------------------------------------------------------------------
    # Private pynput callbacks
    # ------------------------------------------------------------------

    def _on_press(self, key) -> None:
        canonical = _canonicalize_key(key)
        if canonical is None:
            return

        with self._lock:
            self._pressed_keys.add(canonical)
            held = frozenset(self._pressed_keys)

        for hotkey_str, callback in list(self._callbacks.items()):
            combo = _parse_hotkey(hotkey_str)
            with self._lock:
                already_active = hotkey_str in self._active_combos
            if combo <= held and not already_active:
                with self._lock:
                    self._active_combos.add(hotkey_str)
                logger.debug("hotkey activated: %s", hotkey_str)
                try:
                    callback()
                except Exception as exc:
                    logger.warning("hotkey callback error (%s): %s", hotkey_str, exc)

    def _on_release(self, key) -> None:
        canonical = _canonicalize_key(key)
        if canonical is None:
            return

        # Fire release callbacks for any active combo that includes this key.
        for hotkey_str, callback in list(self._release_callbacks.items()):
            combo = _parse_hotkey(hotkey_str)
            with self._lock:
                is_active = hotkey_str in self._active_combos
            if is_active and canonical in combo:
                with self._lock:
                    self._active_combos.discard(hotkey_str)
                logger.debug("hotkey released: %s", hotkey_str)
                try:
                    callback()
                except Exception as exc:
                    logger.warning(
                        "hotkey release callback error (%s): %s", hotkey_str, exc
                    )

        with self._lock:
            self._pressed_keys.discard(canonical)
            # Also deactivate combos whose keys are no longer fully held.
            for hotkey_str in list(self._active_combos):
                combo = _parse_hotkey(hotkey_str)
                if canonical in combo:
                    self._active_combos.discard(hotkey_str)
