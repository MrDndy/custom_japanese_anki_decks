from jp_anki_builder.filtering import filter_tokens


def test_filter_tokens_excludes_particles_and_known_words():
    tokens = ["私", "は", "学生", "です"]
    known = {"学生"}
    result = filter_tokens(tokens, known_words=known)
    assert result == ["私", "です"]


def test_filter_tokens_excludes_naa_and_kanji_one_to_ten():
    tokens = [
        "なぁ",
        "一",
        "二",
        "三",
        "四",
        "五",
        "六",
        "七",
        "八",
        "九",
        "十",
        "人",
        "する",
        "為る",
        "いる",
        "居る",
        "てる",
        "この",
        "その",
        "あの",
        "冒険",
    ]
    result = filter_tokens(tokens, known_words=set())
    assert result == ["冒険"]
