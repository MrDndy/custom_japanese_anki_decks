from jp_anki_builder.dedup import exclude_seen


def test_exclude_seen_removes_existing_source_words():
    candidates = ["冒険", "勇者", "冒険"]
    seen = {"冒険"}
    assert exclude_seen(candidates, seen) == ["勇者"]
