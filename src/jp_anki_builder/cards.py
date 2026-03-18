from __future__ import annotations


def build_genanki_model(model_id: int):
    """Build the canonical genanki Model shared by batch and realtime export.

    Both ``build.py`` and ``session.py`` must use this function so that the
    model CSS, fields, and templates are always identical.  Anki overwrites
    model styling on import when the same model_id is encountered, so any
    divergence here would silently corrupt card styling.
    """
    import genanki

    return genanki.Model(
        model_id,
        "JP Vocab Basic (Bidirectional)",
        fields=[{"name": "Kanji"}, {"name": "Reading"}, {"name": "Meaning"}],
        templates=[
            {
                "name": "Forward",
                "qfmt": (
                    "{{#Reading}}<div class=\"jp-reading japanese\" lang=\"ja\">{{Reading}}</div>{{/Reading}}"
                    "<div class=\"jp-kanji japanese\" lang=\"ja\">{{Kanji}}</div>"
                ),
                "afmt": (
                    "{{FrontSide}}<hr id=\"answer\">"
                    "<div class=\"label\">Meaning:</div>"
                    "<div class=\"text en-meaning\">{{Meaning}}</div>"
                ),
            },
            {
                "name": "Reverse",
                "qfmt": (
                    "<div class=\"label\">Meaning:</div>"
                    "<div class=\"text en-meaning\">{{Meaning}}</div>"
                ),
                "afmt": (
                    "{{FrontSide}}<hr id=\"answer\">"
                    "{{#Reading}}<div class=\"jp-reading japanese\" lang=\"ja\">{{Reading}}</div>{{/Reading}}"
                    "<div class=\"jp-kanji japanese\" lang=\"ja\">{{Kanji}}</div>"
                ),
            },
        ],
        css="""
.card {
  font-family: "Noto Sans Japanese";
  font-size: 20px;
  text-align: center;
}

@font-face {
  font-family: "Noto Sans Japanese";
  src: url("_NotoSansCJKjp-Regular.woff2") format("woff2");
}

.japanese {
  font-family: "Noto Sans Japanese";
}

.jp-kanji {
  font-size: 42px;
  line-height: 1.2;
}

.jp-reading {
  font-size: 28px;
  color: #c0c0c0;
  line-height: 1.2;
  margin-bottom: 4px;
}

.label {
  font-size: 14px;
  color: #c0c0c0;
  margin-top: 8px;
}

.text {
  font-family: "Noto Sans Japanese";
}

.en-meaning {
  font-size: 30px;
  margin-top: 6px;
}
""",
    )


def build_deck_name(source: str, volume: str | None, chapter: str | None) -> str:
    parts = [source]
    if volume:
        parts.append(f"Vol{volume}")
    if chapter:
        parts.append(f"Ch{chapter}")
    return "::".join(parts)


def build_note_fields(
    word: str,
    reading: str,
    meanings: list[str],
) -> dict[str, str]:
    return {
        "kanji": word,
        "reading": reading,
        "meaning": "; ".join(meanings),
    }
