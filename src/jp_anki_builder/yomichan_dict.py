"""Yomichan/Yomitan dictionary ZIP parser and lookup."""
from __future__ import annotations

import json
import logging
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class YomichanEntry:
    expression: str
    reading: str
    meanings: list[str]  # flattened glossary text
    tags: list[str]      # definition tags
    score: int           # popularity/frequency score
    rules: str           # inflection rules (e.g., "v5", "vs")


@dataclass
class YomichanDictionary:
    title: str
    revision: str
    entries: dict[str, list[YomichanEntry]] = field(default_factory=dict)

    @classmethod
    def from_zip(cls, zip_path: Path) -> YomichanDictionary:
        """Parse a Yomichan-format ZIP file."""
        try:
            zf = zipfile.ZipFile(zip_path, "r")
        except (zipfile.BadZipFile, OSError) as exc:
            raise ValueError(f"Cannot open Yomichan dictionary ZIP {zip_path}: {exc}") from exc

        with zf:
            # Parse index.json
            try:
                index_data = json.loads(zf.read("index.json").decode("utf-8"))
            except KeyError:
                raise ValueError(f"Missing index.json in {zip_path}")
            except (json.JSONDecodeError, UnicodeDecodeError) as exc:
                raise ValueError(f"Corrupt index.json in {zip_path}: {exc}") from exc

            title = index_data.get("title", "")
            revision = index_data.get("revision", "")

            # Parse tag banks (all tag_bank_N.json files)
            tag_map: dict[str, str] = {}
            names = zf.namelist()
            tag_bank_names = sorted(
                n for n in names if n.startswith("tag_bank_") and n.endswith(".json")
            )
            for tb_name in tag_bank_names:
                try:
                    tag_data = json.loads(zf.read(tb_name).decode("utf-8"))
                    for tag_entry in tag_data:
                        # [name, category, order, notes, score]
                        if isinstance(tag_entry, list) and len(tag_entry) >= 4:
                            tag_name = tag_entry[0]
                            tag_notes = tag_entry[3] if len(tag_entry) > 3 else ""
                            tag_map[tag_name] = tag_notes or tag_name
                except (json.JSONDecodeError, UnicodeDecodeError) as exc:
                    logger.warning("Skipping corrupt %s in %s: %s", tb_name, zip_path, exc)

            # Parse term banks (all term_bank_N.json files)
            entries: dict[str, list[YomichanEntry]] = {}
            term_bank_names = sorted(
                n for n in names if n.startswith("term_bank_") and n.endswith(".json")
            )
            for tb_name in term_bank_names:
                try:
                    term_data = json.loads(zf.read(tb_name).decode("utf-8"))
                except (json.JSONDecodeError, UnicodeDecodeError) as exc:
                    logger.warning("Skipping corrupt %s in %s: %s", tb_name, zip_path, exc)
                    continue

                for raw in term_data:
                    # Each entry: [expression, reading, definitionTags, rules, score, [glossary...], sequence, termTags]
                    if not isinstance(raw, list) or len(raw) < 6:
                        continue
                    expression = raw[0] or ""
                    reading = raw[1] or ""
                    definition_tags_str = raw[2] or ""
                    rules = raw[3] or ""
                    score = raw[4] if isinstance(raw[4], int) else 0
                    glossary_list = raw[5] if isinstance(raw[5], list) else []

                    tags = [t for t in definition_tags_str.split() if t]
                    meanings = [_flatten_glossary(g) for g in glossary_list]
                    meanings = [m for m in meanings if m]

                    entry = YomichanEntry(
                        expression=expression,
                        reading=reading,
                        meanings=meanings,
                        tags=tags,
                        score=score,
                        rules=rules,
                    )
                    entries.setdefault(expression, []).append(entry)

        logger.info(
            "Loaded Yomichan dictionary %r (%s): %d expressions",
            title, revision, len(entries),
        )
        return cls(title=title, revision=revision, entries=entries)

    def lookup(self, word: str) -> list[YomichanEntry]:
        """Look up a word. Returns all matching entries."""
        return self.entries.get(word, [])


def _flatten_glossary(glossary) -> str:
    """Flatten a glossary item to plain text.

    Glossary items can be:
    - str: use directly
    - dict with type "structured-content": recurse into content tree
    - dict with type "image": skip
    - dict with type "text": return text field
    - dict with type "link": return attr href or text
    """
    if isinstance(glossary, str):
        return glossary.strip()
    if not isinstance(glossary, dict):
        return ""
    content_type = glossary.get("type", "")
    if content_type == "text":
        return str(glossary.get("text", "")).strip()
    if content_type == "structured-content":
        return _flatten_structured_content(glossary.get("content", ""))
    if content_type == "image":
        return ""
    # Fallback: try "text" field
    return str(glossary.get("text", "")).strip()


def _flatten_structured_content(content) -> str:
    """Recursively extract plain text from structured-content nodes."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = [_flatten_structured_content(item) for item in content]
        return " ".join(p for p in parts if p).strip()
    if isinstance(content, dict):
        tag = content.get("tag", "")
        # For block elements, add spacing
        inner = _flatten_structured_content(content.get("content", ""))
        if tag in ("br",):
            return " "
        return inner
    return ""
