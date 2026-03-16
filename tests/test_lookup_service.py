from __future__ import annotations

import pytest

from jp_anki_builder.lookup_service import LookupResult, LookupService, TextLookupResponse


@pytest.fixture
def service(tmp_path):
    """LookupService pointing at a temporary data directory (no real dictionary)."""
    return LookupService(data_dir=str(tmp_path), online_dict="off")


class TestLookupServiceReturnTypes:
    def test_returns_text_lookup_response(self, service):
        result = service.lookup("昨日は友達と食べに行った")
        assert isinstance(result, TextLookupResponse)

    def test_words_are_lookup_results(self, service):
        result = service.lookup("昨日は友達と食べに行った")
        assert isinstance(result.words, list)
        for word in result.words:
            assert isinstance(word, LookupResult)

    def test_raw_text_preserved(self, service):
        text = "昨日は友達と食べに行った"
        result = service.lookup(text)
        assert result.raw_text == text

    def test_processing_time_measured(self, service):
        result = service.lookup("日本語")
        assert result.processing_time_ms >= 0


class TestParticleFiltering:
    def test_ha_particle_excluded(self, service):
        result = service.lookup("昨日は友達と食べに行った")
        lemmas = [w.dictionary_form for w in result.words]
        assert "は" not in lemmas

    def test_to_particle_excluded(self, service):
        result = service.lookup("昨日は友達と食べに行った")
        lemmas = [w.dictionary_form for w in result.words]
        assert "と" not in lemmas

    def test_ni_particle_excluded(self, service):
        result = service.lookup("昨日は友達と食べに行った")
        lemmas = [w.dictionary_form for w in result.words]
        assert "に" not in lemmas


class TestLemmatization:
    def test_verb_taberu_lemmatized(self, service):
        result = service.lookup("昨日は友達と食べに行った")
        lemmas = [w.dictionary_form for w in result.words]
        assert "食べる" in lemmas

    def test_verb_iku_lemmatized(self, service):
        result = service.lookup("昨日は友達と食べに行った")
        lemmas = [w.dictionary_form for w in result.words]
        assert "行く" in lemmas

    def test_content_words_present(self, service):
        result = service.lookup("昨日は友達と食べに行った")
        lemmas = [w.dictionary_form for w in result.words]
        # 昨日 and 友達 should survive filtering
        assert any(lemma in {"昨日", "友達"} for lemma in lemmas)


class TestLookupResultFields:
    def test_surface_is_string(self, service):
        result = service.lookup("食べる")
        assert all(isinstance(w.surface, str) for w in result.words)

    def test_dictionary_form_is_string(self, service):
        result = service.lookup("食べる")
        assert all(isinstance(w.dictionary_form, str) for w in result.words)

    def test_reading_is_string(self, service):
        result = service.lookup("食べる")
        assert all(isinstance(w.reading, str) for w in result.words)

    def test_meanings_is_list(self, service):
        result = service.lookup("食べる")
        assert all(isinstance(w.meanings, list) for w in result.words)

    def test_part_of_speech_is_string(self, service):
        result = service.lookup("食べる")
        assert all(isinstance(w.part_of_speech, str) for w in result.words)

    def test_confidence_is_float(self, service):
        result = service.lookup("食べる")
        assert all(isinstance(w.confidence, float) for w in result.words)

    def test_jlpt_level_is_string(self, service):
        result = service.lookup("食べる")
        assert all(isinstance(w.jlpt_level, str) for w in result.words)

    def test_is_in_vocab_db_is_bool(self, service):
        result = service.lookup("食べる")
        assert all(isinstance(w.is_in_vocab_db, bool) for w in result.words)

    def test_words_not_in_empty_vocab_db(self, service):
        result = service.lookup("食べる")
        assert all(not w.is_in_vocab_db for w in result.words)


class TestJlptLevels:
    def test_jlpt_level_empty_when_no_data_file(self, service):
        # No jlpt_levels.json in tmp_path, so all levels should be empty string
        result = service.lookup("食べる")
        for word in result.words:
            assert word.jlpt_level == ""


class TestContextManager:
    def test_can_use_as_context_manager(self, tmp_path):
        with LookupService(data_dir=str(tmp_path)) as svc:
            result = svc.lookup("日本語")
        assert isinstance(result, TextLookupResponse)


class TestMultipleWords:
    def test_sentence_produces_multiple_words(self, service):
        result = service.lookup("昨日は友達と食べに行った")
        assert len(result.words) >= 2
