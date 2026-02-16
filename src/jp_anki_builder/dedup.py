def exclude_seen(candidates: list[str], seen: set[str]) -> list[str]:
    kept: list[str] = []
    local_seen: set[str] = set()

    for token in candidates:
        if token in seen or token in local_seen:
            continue
        local_seen.add(token)
        kept.append(token)

    return kept
