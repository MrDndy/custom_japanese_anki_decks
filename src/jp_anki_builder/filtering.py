DEFAULT_PARTICLES = {
    "は",
    "が",
    "を",
    "に",
    "で",
    "と",
    "も",
    "の",
    "へ",
    "か",
    "なぁ",
    "一",
    "二",
    "三",
    "四",
    "五",
    "六",
    "七",
    "八",
    "九",
    "十",
    "人",
}


def filter_tokens(tokens: list[str], known_words: set[str]) -> list[str]:
    return [token for token in tokens if token not in DEFAULT_PARTICLES and token not in known_words]
