from jp_anki_builder.filtering import filter_tokens


def test_filter_tokens_excludes_particles_and_known_words():
    tokens = ["私", "は", "学生", "です"]
    known = {"学生"}
    result = filter_tokens(tokens, known_words=known)
    assert result == ["私", "です"]
