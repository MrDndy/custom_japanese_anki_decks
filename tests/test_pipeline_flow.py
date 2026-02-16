from jp_anki_builder.pipeline import Pipeline


def test_run_executes_stages_in_order(monkeypatch):
    p = Pipeline()

    monkeypatch.setattr(
        p,
        "scan",
        lambda images, source, run_id, ocr_mode="sidecar": {"stage": "scan", "image_count": 1},
    )
    monkeypatch.setattr(
        p,
        "review",
        lambda source, run_id, exclude=None, save_excluded_to_known=False: {
            "stage": "review",
            "approved_count": 1,
        },
    )
    monkeypatch.setattr(
        p,
        "build",
        lambda source, run_id, volume=None, chapter=None: {
            "stage": "build",
            "note_count": 2,
            "package_path": "out.apkg",
        },
    )

    result = p.run_all(images="img", source="src", run_id="r1")
    assert result["scan"]["stage"] == "scan"
    assert result["review"]["stage"] == "review"
    assert result["build"]["stage"] == "build"
