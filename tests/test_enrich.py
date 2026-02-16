from jp_anki_builder.enrich import enrich_word


class Offline:
    def lookup(self, word):
        return None


class Online:
    def lookup(self, word):
        return {"reading": "ぼうけん", "meanings": ["adventure", "quest", "journey", "venture"]}


def test_enrich_word_uses_fallback_and_caps_meanings():
    data = enrich_word("冒険", offline=Offline(), online=Online(), max_meanings=3)
    assert data["reading"] == "ぼうけん"
    assert data["meanings"] == ["adventure", "quest", "journey"]
