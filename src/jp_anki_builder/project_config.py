"""Project-level and source-level configuration.

Loads defaults from config files so CLI invocations can be shorter.

Lookup order (later overrides earlier):
1. data/.jp-anki.json          (project defaults)
2. data/<source>/.jp-anki.json (source-specific overrides)
3. CLI flags                   (always win)
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field, fields
from pathlib import Path

logger = logging.getLogger(__name__)

CONFIG_FILENAME = ".jp-anki.json"


@dataclass
class ProjectDefaults:
    ocr_mode: str | None = None
    ocr_language: str | None = None
    tesseract_cmd: str | None = None
    online_dict: str | None = None
    data_dir: str | None = None
    no_preprocess: bool | None = None
    volume: str | None = None
    chapter: str | None = None

    def merge(self, other: ProjectDefaults) -> ProjectDefaults:
        """Return a new ProjectDefaults with non-None values from *other* taking precedence."""
        merged = {}
        for f in fields(self):
            other_val = getattr(other, f.name)
            merged[f.name] = other_val if other_val is not None else getattr(self, f.name)
        return ProjectDefaults(**merged)


def load_project_config(data_dir: str = "data", source: str | None = None) -> ProjectDefaults:
    """Load config from project and source config files."""
    base = Path(data_dir)
    result = ProjectDefaults()

    # Project-level config
    project_cfg = base / CONFIG_FILENAME
    if project_cfg.exists():
        logger.debug("loading project config from %s", project_cfg)
        result = result.merge(_read_config(project_cfg))

    # Source-level config
    if source:
        source_cfg = base / source / CONFIG_FILENAME
        if source_cfg.exists():
            logger.debug("loading source config from %s", source_cfg)
            result = result.merge(_read_config(source_cfg))

    return result


def _read_config(path: Path) -> ProjectDefaults:
    try:
        raw = json.loads(path.read_text(encoding="utf-8-sig"))
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("failed to read config %s: %s", path, exc)
        return ProjectDefaults()

    kwargs = {}
    for f in fields(ProjectDefaults):
        if f.name in raw:
            kwargs[f.name] = raw[f.name]
    return ProjectDefaults(**kwargs)


def apply_defaults(defaults: ProjectDefaults, **cli_kwargs) -> dict:
    """Merge config defaults with CLI kwargs. CLI values (non-None) always win."""
    result = {}
    for f in fields(defaults):
        cli_val = cli_kwargs.get(f.name)
        default_val = getattr(defaults, f.name)
        # CLI value wins if it's explicitly set (not None, and not a typer default sentinel)
        result[f.name] = cli_val if cli_val is not None else default_val
    return result


VALID_KEYS = {f.name for f in fields(ProjectDefaults)}


def _config_path(data_dir: str, source: str | None) -> Path:
    base = Path(data_dir)
    if source:
        return base / source / CONFIG_FILENAME
    return base / CONFIG_FILENAME


def get_config(data_dir: str = "data", source: str | None = None) -> dict:
    """Read the raw config dict for project or source level."""
    path = _config_path(data_dir, source)
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except (json.JSONDecodeError, OSError):
        return {}


def set_config(key: str, value: str, data_dir: str = "data", source: str | None = None) -> dict:
    """Set a config key. Returns the updated config dict."""
    if key not in VALID_KEYS:
        raise ValueError(f"unknown config key: {key!r}. Valid keys: {', '.join(sorted(VALID_KEYS))}")

    path = _config_path(data_dir, source)
    current = get_config(data_dir, source)

    # Coerce booleans
    if key == "no_preprocess":
        current[key] = value.lower() in ("true", "1", "yes")
    else:
        current[key] = value

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(current, indent=2, ensure_ascii=False), encoding="utf-8")
    return current


def unset_config(key: str, data_dir: str = "data", source: str | None = None) -> dict:
    """Remove a config key. Returns the updated config dict."""
    path = _config_path(data_dir, source)
    current = get_config(data_dir, source)
    current.pop(key, None)

    if current:
        path.write_text(json.dumps(current, indent=2, ensure_ascii=False), encoding="utf-8")
    elif path.exists():
        path.unlink()
    return current
