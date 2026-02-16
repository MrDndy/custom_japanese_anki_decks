from jp_anki_builder.cards import build_deck_name, build_bidirectional_fields


def test_build_deck_name_hierarchical():
    assert build_deck_name("MangaA", "02", "07") == "MangaA::Volume02::Chapter07"


def test_build_bidirectional_fields():
    notes = build_bidirectional_fields(word="冒険", reading="ぼうけん", meanings=["adventure"])
    assert len(notes) == 2
    assert notes[0]["front"] == "冒険<br>ぼうけん"
    assert notes[1]["front"] == "adventure"
