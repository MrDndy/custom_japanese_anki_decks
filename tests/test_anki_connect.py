"""Tests for AnkiConnectClient using mocked HTTP responses."""
from __future__ import annotations

import json
from io import BytesIO
from unittest.mock import MagicMock, patch

import pytest

from jp_anki_builder.anki_connect import AnkiConnectClient, _build_note


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _mock_response(body: dict, status: int = 200):
    """Build a fake urllib response object."""
    data = json.dumps(body).encode()
    resp = MagicMock()
    resp.read.return_value = data
    resp.status = status
    resp.__enter__ = lambda s: s
    resp.__exit__ = MagicMock(return_value=False)
    return resp


def _patch_urlopen(body: dict, status: int = 200):
    return patch(
        "urllib.request.urlopen",
        return_value=_mock_response(body, status),
    )


# ---------------------------------------------------------------------------
# is_available
# ---------------------------------------------------------------------------

class TestIsAvailable:
    def test_returns_true_when_version_gte_6(self):
        with _patch_urlopen({"result": 6, "error": None}):
            assert AnkiConnectClient().is_available() is True

    def test_returns_true_for_higher_version(self):
        with _patch_urlopen({"result": 7, "error": None}):
            assert AnkiConnectClient().is_available() is True

    def test_returns_false_when_version_too_low(self):
        with _patch_urlopen({"result": 5, "error": None}):
            assert AnkiConnectClient().is_available() is False

    def test_returns_false_on_connection_error(self):
        import urllib.error
        with patch("urllib.request.urlopen", side_effect=urllib.error.URLError("refused")):
            assert AnkiConnectClient().is_available() is False

    def test_returns_false_on_non_int_result(self):
        with _patch_urlopen({"result": None, "error": None}):
            assert AnkiConnectClient().is_available() is False


# ---------------------------------------------------------------------------
# can_add_note
# ---------------------------------------------------------------------------

class TestCanAddNote:
    def test_returns_true_when_anki_says_can_add(self):
        with _patch_urlopen({"result": [True], "error": None}):
            assert AnkiConnectClient().can_add_note("Deck", "食べる", "たべる") is True

    def test_returns_false_when_anki_says_duplicate(self):
        with _patch_urlopen({"result": [False], "error": None}):
            assert AnkiConnectClient().can_add_note("Deck", "食べる", "たべる") is False

    def test_returns_true_on_connection_error(self):
        """Safe default: assume addable when Anki is unreachable."""
        import urllib.error
        with patch("urllib.request.urlopen", side_effect=urllib.error.URLError("refused")):
            assert AnkiConnectClient().can_add_note("Deck", "食べる", "たべる") is True

    def test_returns_true_on_empty_result(self):
        with _patch_urlopen({"result": [], "error": None}):
            assert AnkiConnectClient().can_add_note("Deck", "食べる", "たべる") is True

    def test_request_contains_note_fields(self):
        """Verify the request payload includes the expression and reading."""
        captured = []

        def fake_urlopen(req, timeout=None):
            captured.append(json.loads(req.data.decode()))
            return _mock_response({"result": [True], "error": None})

        with patch("urllib.request.urlopen", fake_urlopen):
            AnkiConnectClient().can_add_note("MyDeck", "行く", "いく")

        assert len(captured) == 1
        note = captured[0]["params"]["notes"][0]
        assert note["fields"]["Kanji"] == "行く"
        assert note["fields"]["Reading"] == "いく"
        assert note["deckName"] == "MyDeck"


# ---------------------------------------------------------------------------
# add_note
# ---------------------------------------------------------------------------

class TestAddNote:
    def test_returns_note_id_on_success(self):
        with _patch_urlopen({"result": 1234567890, "error": None}):
            note_id = AnkiConnectClient().add_note("Deck", "行く", "いく", "to go")
            assert note_id == 1234567890

    def test_returns_none_on_error(self):
        with _patch_urlopen({"result": None, "error": "duplicate note"}):
            assert AnkiConnectClient().add_note("Deck", "行く", "いく", "to go") is None

    def test_returns_none_on_connection_error(self):
        import urllib.error
        with patch("urllib.request.urlopen", side_effect=urllib.error.URLError("refused")):
            assert AnkiConnectClient().add_note("Deck", "行く", "いく", "to go") is None

    def test_request_payload(self):
        """Verify the note payload is built correctly."""
        captured = []

        def fake_urlopen(req, timeout=None):
            captured.append(json.loads(req.data.decode()))
            return _mock_response({"result": 999, "error": None})

        with patch("urllib.request.urlopen", fake_urlopen):
            AnkiConnectClient().add_note("MyDeck", "見る", "みる", "to see; to look")

        payload = captured[0]
        assert payload["action"] == "addNote"
        note = payload["params"]["note"]
        assert note["deckName"] == "MyDeck"
        assert note["fields"]["Kanji"] == "見る"
        assert note["fields"]["Reading"] == "みる"
        assert note["fields"]["Meaning"] == "to see; to look"


# ---------------------------------------------------------------------------
# build_note helper
# ---------------------------------------------------------------------------

class TestBuildNote:
    def test_structure(self):
        note = _build_note("TestDeck", "食べる", "たべる", "to eat")
        assert note["deckName"] == "TestDeck"
        assert note["modelName"] == "JP Vocab Basic (Bidirectional)"
        assert note["fields"] == {
            "Kanji": "食べる",
            "Reading": "たべる",
            "Meaning": "to eat",
        }
        assert note["options"]["allowDuplicate"] is False


# ---------------------------------------------------------------------------
# SessionBuffer AnkiConnect integration
# ---------------------------------------------------------------------------

class TestSessionBufferAnkiConnect:
    """Verify SessionBuffer.add_word() respects the anki_client dedup."""

    def _make_result(self, dictionary_form: str = "食べる", reading: str = "たべる"):
        from jp_anki_builder.lookup_service import LookupResult
        return LookupResult(
            surface=dictionary_form,
            dictionary_form=dictionary_form,
            reading=reading,
            meanings=["to eat"],
            part_of_speech="動詞",
            confidence=1.0,
            jlpt_level="N4",
            is_in_vocab_db=False,
        )

    def test_word_skipped_when_anki_says_duplicate(self):
        from jp_anki_builder.realtime.session import SessionBuffer

        mock_client = MagicMock()
        mock_client.can_add_note.return_value = False

        buf = SessionBuffer(anki_client=mock_client)
        added = buf.add_word(self._make_result(), source_text="食べる")
        assert added is False
        assert len(buf) == 0

    def test_word_added_when_anki_says_ok(self):
        from jp_anki_builder.realtime.session import SessionBuffer

        mock_client = MagicMock()
        mock_client.can_add_note.return_value = True

        buf = SessionBuffer(anki_client=mock_client)
        added = buf.add_word(self._make_result(), source_text="食べる")
        assert added is True
        assert len(buf) == 1

    def test_word_added_when_no_anki_client(self):
        from jp_anki_builder.realtime.session import SessionBuffer

        buf = SessionBuffer()
        added = buf.add_word(self._make_result(), source_text="食べる")
        assert added is True

    def test_anki_exception_does_not_crash(self):
        """If AnkiConnect raises unexpectedly, word is still added."""
        from jp_anki_builder.realtime.session import SessionBuffer

        mock_client = MagicMock()
        mock_client.can_add_note.side_effect = RuntimeError("unexpected")

        buf = SessionBuffer(anki_client=mock_client)
        added = buf.add_word(self._make_result(), source_text="食べる")
        assert added is True  # safe fallback
