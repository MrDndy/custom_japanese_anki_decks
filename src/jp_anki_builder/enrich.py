from __future__ import annotations


def enrich_word(
    word: str,
    offline,
    online,
    max_meanings: int = 3,
) -> dict:
    entry = offline.lookup(word) or online.lookup(word)
    result: dict = {"word": word, "reading": "", "meanings": []}

    if entry:
        result["reading"] = entry.get("reading", "")
        result["meanings"] = entry.get("meanings", [])[:max_meanings]

    return result
