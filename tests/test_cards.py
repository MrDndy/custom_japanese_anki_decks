from jp_anki_builder.cards import build_deck_name, build_note_fields


def test_build_deck_name_hierarchical():
    assert build_deck_name("MangaA", "02", "07") == "MangaA::Vol02::Ch07"


def test_build_note_fields_uses_dedicated_reading_field():
    note = build_note_fields(word="冒険", reading="ぼうけん", meanings=["adventure"])
    assert note["kanji"] == "冒険"
    assert note["reading"] == "ぼうけん"
    assert note["meaning"] == "adventure"
