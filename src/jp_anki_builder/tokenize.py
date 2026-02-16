from __future__ import annotations

import re


JAPANESE_CHUNK_RE = re.compile(r"[\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff]+")


def extract_candidates(text: str) -> list[str]:
    candidates = JAPANESE_CHUNK_RE.findall(text)
    seen: set[str] = set()
    result: list[str] = []
    for token in candidates:
        if token in seen:
            continue
        seen.add(token)
        result.append(token)
    return result
