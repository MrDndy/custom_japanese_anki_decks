from jp_anki_builder.pipeline import Pipeline


def test_run_executes_stages_in_order():
    p = Pipeline()
    assert p.run_all() == ["scan", "review", "build"]
