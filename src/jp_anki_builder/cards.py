def build_deck_name(source: str, volume: str | None, chapter: str | None) -> str:
    parts = [source]
    if volume:
        parts.append(f"Vol{volume}")
    if chapter:
        parts.append(f"Ch{chapter}")
    return "::".join(parts)


def build_note_fields(word: str, reading: str, meanings: list[str]) -> dict[str, str]:
    return {
        "kanji": word,
        "reading": reading,
        "meaning": "; ".join(meanings),
    }
