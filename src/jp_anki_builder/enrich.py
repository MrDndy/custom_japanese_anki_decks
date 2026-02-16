def enrich_word(word: str, offline, online, max_meanings: int = 3) -> dict:
    entry = offline.lookup(word) or online.lookup(word)
    if not entry:
        return {"word": word, "reading": "", "meanings": []}

    return {
        "word": word,
        "reading": entry.get("reading", ""),
        "meanings": entry.get("meanings", [])[:max_meanings],
    }
