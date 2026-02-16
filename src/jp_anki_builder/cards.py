def build_deck_name(source: str, volume: str | None, chapter: str | None) -> str:
    parts = [source]
    if volume:
        parts.append(f"Volume{volume}")
    if chapter:
        parts.append(f"Chapter{chapter}")
    return "::".join(parts)


def build_bidirectional_fields(word: str, reading: str, meanings: list[str]) -> list[dict]:
    meaning_text = "; ".join(meanings)
    a_front = f"{word}<br>{reading}" if reading else word
    return [
        {"front": a_front, "back": meaning_text},
        {"front": meaning_text, "back": a_front},
    ]
