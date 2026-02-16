from jp_anki_builder.config import RunPaths


def test_run_paths_are_scoped():
    paths = RunPaths(base_dir="data", source_id="manga_a", run_id="r1")
    assert paths.run_dir.as_posix().endswith("data/runs/r1")
    assert paths.source_seen_words.as_posix().endswith("data/sources/manga_a/seen_words.json")
