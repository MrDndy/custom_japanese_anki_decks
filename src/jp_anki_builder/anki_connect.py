"""Lightweight AnkiConnect REST API client.

AnkiConnect (https://foosoft.net/projects/anki-connect/) is a free add-on for
Anki that exposes a local HTTP JSON-RPC server on port 8765.  This module
provides a minimal client suitable for real-time duplicate detection and direct
note creation.

All network calls use only the standard library (``urllib``) to avoid adding a
dependency.  Every public method catches connection errors and returns a safe
default so that callers work correctly whether Anki is running or not.
"""
from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request
from typing import Any

logger = logging.getLogger(__name__)

_ANKI_CONNECT_VERSION = 6
_DEFAULT_TIMEOUT_S = 2.0
_MODEL_NAME = "JP Vocab Basic (Bidirectional)"


class AnkiConnectClient:
    """Client for the AnkiConnect REST API (localhost:<port>).

    All methods return a safe default (False / None) when Anki is not running
    or the request fails for any reason — callers never need to handle
    connection errors explicitly.
    """

    def __init__(self, port: int = 8765, timeout: float = _DEFAULT_TIMEOUT_S) -> None:
        self._url = f"http://localhost:{port}"
        self._timeout = timeout

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def is_available(self) -> bool:
        """Return True if Anki is running with AnkiConnect installed."""
        result = self._request("version")
        return isinstance(result, int) and result >= _ANKI_CONNECT_VERSION

    def can_add_note(self, deck: str, expression: str, reading: str) -> bool:
        """Return True if *expression* is NOT already in the user's collection.

        Uses the AnkiConnect ``canAddNotes`` action.  Returns True (can add)
        when Anki is unavailable so that callers never silently drop words.
        """
        note = _build_note(deck, expression, reading, meaning="")
        result = self._request("canAddNotes", params={"notes": [note]})
        if not isinstance(result, list) or len(result) == 0:
            # Fallback: assume addable if we can't reach Anki.
            return True
        return bool(result[0])

    def add_note(
        self,
        deck: str,
        expression: str,
        reading: str,
        meaning: str,
    ) -> int | None:
        """Add a note to Anki and return its note ID, or None on failure."""
        note = _build_note(deck, expression, reading, meaning)
        result = self._request("addNote", params={"note": note})
        if isinstance(result, int):
            return result
        return None

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _request(self, action: str, params: dict[str, Any] | None = None) -> Any:
        """Send a JSON-RPC request to AnkiConnect.

        Returns the ``result`` field of the response, or None on any error.
        """
        payload = {
            "action": action,
            "version": _ANKI_CONNECT_VERSION,
        }
        if params is not None:
            payload["params"] = params

        data = json.dumps(payload).encode()
        req = urllib.request.Request(
            self._url,
            data=data,
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=self._timeout) as resp:
                body = json.loads(resp.read().decode())
        except (urllib.error.URLError, OSError, json.JSONDecodeError, TimeoutError) as exc:
            logger.debug("AnkiConnect request failed (%s): %s", action, exc)
            return None

        if body.get("error"):
            logger.debug("AnkiConnect error (%s): %s", action, body["error"])
            return None
        return body.get("result")


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _build_note(deck: str, expression: str, reading: str, meaning: str) -> dict:
    """Build the AnkiConnect note dict for our JP Vocab Basic model."""
    return {
        "deckName": deck,
        "modelName": _MODEL_NAME,
        "fields": {
            "Kanji": expression,
            "Reading": reading,
            "Meaning": meaning,
        },
        "options": {
            "allowDuplicate": False,
            "duplicateScope": "deck",
        },
        "tags": [],
    }
