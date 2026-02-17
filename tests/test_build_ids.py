from jp_anki_builder.build import _deck_id, _model_id


def test_model_id_is_stable():
    assert _model_id() == _model_id()


def test_deck_id_is_stable_per_deck_name():
    assert _deck_id("Miharu::Vol01::Ch00") == _deck_id("Miharu::Vol01::Ch00")
    assert _deck_id("Miharu::Vol01::Ch00") != _deck_id("Miharu::Vol01::Ch01")
