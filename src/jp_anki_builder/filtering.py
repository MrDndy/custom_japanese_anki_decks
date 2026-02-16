DEFAULT_PARTICLES = {"は", "が", "を", "に", "で", "と", "も", "の", "へ", "か"}


def filter_tokens(tokens: list[str], known_words: set[str]) -> list[str]:
    return [token for token in tokens if token not in DEFAULT_PARTICLES and token not in known_words]
