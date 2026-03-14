from __future__ import annotations

import gzip
import json
import logging
import tempfile
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path

from jp_anki_builder.jlpt import JLPT_DATA_FILENAME

logger = logging.getLogger(__name__)

DEFAULT_JMDICT_E_URL = "https://www.edrdg.org/pub/Nihongo/JMdict_e.gz"


@dataclass
class DictInstallSummary:
    provider: str
    source_url: str
    output_path: str
    entry_count: int


def install_jmdict_offline_json(
    base_dir: str = "data",
    source_url: str = DEFAULT_JMDICT_E_URL,
    max_meanings: int = 3,
) -> DictInstallSummary:
    output_path = Path(base_dir) / "dictionaries" / "offline.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.NamedTemporaryFile(suffix=".gz", delete=False) as tmp:
        tmp_path = Path(tmp.name)

    try:
        with urllib.request.urlopen(source_url, timeout=60) as resp:
            tmp_path.write_bytes(resp.read())

        with gzip.open(tmp_path, "rb") as fh:
            payload = _build_offline_payload_from_jmdict_xml_bytes(fh.read(), max_meanings=max_meanings)
    finally:
        if tmp_path.exists():
            tmp_path.unlink()

    output_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return DictInstallSummary(
        provider="jmdict_e",
        source_url=source_url,
        output_path=str(output_path),
        entry_count=len(payload),
    )


def _build_offline_payload_from_jmdict_xml_bytes(xml_bytes: bytes, max_meanings: int = 3) -> dict[str, dict]:
    root = ET.fromstring(xml_bytes)
    data: dict[str, dict] = {}

    for entry in root.findall("entry"):
        keb = [el.text.strip() for el in entry.findall("./k_ele/keb") if el.text and el.text.strip()]
        reb = [el.text.strip() for el in entry.findall("./r_ele/reb") if el.text and el.text.strip()]
        meanings = _extract_english_glosses(entry)
        if not meanings:
            continue
        meanings = meanings[:max_meanings]

        forms = keb if keb else reb
        if not forms:
            continue

        for form in forms:
            if form in data:
                continue
            reading = form if form in reb else (reb[0] if reb else "")
            data[form] = {"reading": reading, "meanings": meanings}

    return data


def _extract_english_glosses(entry: ET.Element) -> list[str]:
    out: list[str] = []
    for gloss in entry.findall("./sense/gloss"):
        lang = gloss.attrib.get("{http://www.w3.org/XML/1998/namespace}lang")
        if lang not in (None, "", "eng"):
            continue
        text = (gloss.text or "").strip()
        if not text or text in out:
            continue
        out.append(text)
    return out


def install_jlpt_from_file(
    source_path: str,
    base_dir: str = "data",
) -> DictInstallSummary:
    """Install JLPT level data from a JSON file.

    Expected format: {"word": level, ...} where level is 1-5.
    Example: {"食べる": 5, "冒険": 2, ...}
    """
    src = Path(source_path)
    if not src.exists():
        raise FileNotFoundError(f"JLPT source file not found: {source_path}")

    raw = json.loads(src.read_text(encoding="utf-8-sig"))
    # Validate: all values must be ints 1-5
    data: dict[str, int] = {}
    for word, level in raw.items():
        lvl = int(level)
        if lvl < 1 or lvl > 5:
            logger.warning("skipping %r: invalid JLPT level %d", word, lvl)
            continue
        data[word] = lvl

    output_path = Path(base_dir) / "dictionaries" / JLPT_DATA_FILENAME
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

    return DictInstallSummary(
        provider="jlpt_json",
        source_url=str(src),
        output_path=str(output_path),
        entry_count=len(data),
    )
