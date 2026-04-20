# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for JP Anki Builder.

Produces a single-directory distribution at dist/jp-anki-build/.
Run via:  python packaging/build.py
"""
from __future__ import annotations

import importlib.util
import os
from pathlib import Path

from PyInstaller.building.api import COLLECT, EXE, PYZ
from PyInstaller.building.build_main import Analysis

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

ROOT = Path(SPECPATH).parent  # project root (one level up from packaging/)
SRC = ROOT / "src"

def _pkg_dir(module_name: str) -> str:
    """Return the directory containing an installed package."""
    spec = importlib.util.find_spec(module_name)
    if spec is None or spec.origin is None:
        raise RuntimeError(f"Package {module_name!r} not found — is it installed?")
    return os.path.dirname(spec.origin)


# ---------------------------------------------------------------------------
# Entry point script (wraps the Typer CLI)
# ---------------------------------------------------------------------------

_ENTRY_SCRIPT = str(ROOT / "packaging" / "_entry.py")

# Create the tiny entry script if it doesn't exist yet.
if not os.path.exists(_ENTRY_SCRIPT):
    with open(_ENTRY_SCRIPT, "w", encoding="utf-8") as f:
        f.write(
            "import sys, os\n"
            "# Ensure src/ is on the path for editable installs\n"
            "sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))\n"
            "from jp_anki_builder.cli import app\n"
            "app()\n"
        )

# ---------------------------------------------------------------------------
# Data files to bundle
# ---------------------------------------------------------------------------

datas = []

# unidic-lite dictionary (required by fugashi/MeCab)
try:
    _unidic_dir = _pkg_dir("unidic_lite")
    _dicdir = os.path.join(_unidic_dir, "dicdir")
    if os.path.isdir(_dicdir):
        datas.append((_dicdir, os.path.join("unidic_lite", "dicdir")))
except RuntimeError:
    print("[WARN] unidic_lite not found — fugashi tokenization will not work in the packaged app")

# sudachidict_core dictionary (required by SudachiPy)
try:
    _sudachi_dir = _pkg_dir("sudachidict_core")
    _resources = os.path.join(_sudachi_dir, "resources")
    if os.path.isdir(_resources):
        datas.append((_resources, os.path.join("sudachidict_core", "resources")))
except RuntimeError:
    print("[WARN] sudachidict_core not found — Sudachi normalization will not work in the packaged app")

# genanki templates
try:
    _genanki_dir = _pkg_dir("genanki")
    datas.append((_genanki_dir, "genanki"))
except RuntimeError:
    pass

# Project source
datas.append((str(SRC / "jp_anki_builder"), "jp_anki_builder"))

# ---------------------------------------------------------------------------
# Hidden imports
# ---------------------------------------------------------------------------

hiddenimports = [
    # Core pipeline
    "jp_anki_builder",
    "jp_anki_builder.cli",
    "jp_anki_builder.pipeline",
    "jp_anki_builder.scan",
    "jp_anki_builder.review",
    "jp_anki_builder.build",
    "jp_anki_builder.cards",
    "jp_anki_builder.ocr",
    "jp_anki_builder.tokenize",
    "jp_anki_builder.normalization",
    "jp_anki_builder.deinflect",
    "jp_anki_builder.dictionary",
    "jp_anki_builder.filtering",
    "jp_anki_builder.enrich",
    "jp_anki_builder.jlpt",
    "jp_anki_builder.vocab_db",
    "jp_anki_builder.config",
    "jp_anki_builder.project_config",
    "jp_anki_builder.path_inference",
    "jp_anki_builder.dedup",
    "jp_anki_builder.format_handlers",
    "jp_anki_builder.ocr_corrections",
    "jp_anki_builder.yomichan_dict",
    "jp_anki_builder.subtitle_extractor",
    "jp_anki_builder.lookup_service",
    "jp_anki_builder.anki_connect",
    "jp_anki_builder.dict_install",
    "jp_anki_builder.screen_capture",
    # Region detectors
    "jp_anki_builder.region_detectors",
    "jp_anki_builder.region_detectors.paddleocr_detector",
    # GUI
    "jp_anki_builder.gui",
    "jp_anki_builder.gui.app",
    "jp_anki_builder.gui.main_window",
    "jp_anki_builder.gui.review_panel",
    "jp_anki_builder.gui.workers",
    # Realtime overlay
    "jp_anki_builder.realtime",
    "jp_anki_builder.realtime.app",
    "jp_anki_builder.realtime.controller",
    "jp_anki_builder.realtime.overlay",
    "jp_anki_builder.realtime.buffer_panel",
    "jp_anki_builder.realtime.hotkeys",
    "jp_anki_builder.realtime.ocr_worker",
    "jp_anki_builder.realtime.session",
    # NLP
    "fugashi",
    "unidic_lite",
    "sudachipy",
    "sudachidict_core",
    # Dependencies
    "typer",
    "click",
    "genanki",
    "natsort",
    "PIL",
    "mss",
    "pynput",
    "pynput.keyboard",
    "pynput.keyboard._win32",
    "pynput.mouse",
    "pynput.mouse._win32",
    "pysubs2",
    # PySide6
    "PySide6",
    "PySide6.QtCore",
    "PySide6.QtWidgets",
    "PySide6.QtGui",
]

# ---------------------------------------------------------------------------
# Excludes (keep bundle size down)
# ---------------------------------------------------------------------------

excludes = [
    # PaddleOCR is too large to bundle — document as optional install
    "paddle",
    "paddlepaddle",
    "paddleocr",
    # Test frameworks
    "pytest",
    "_pytest",
    "hypothesis",
    # Dev tools
    "IPython",
    "jupyter",
    "notebook",
    "sphinx",
    "setuptools",
    "pip",
    # Unused heavy packages
    "matplotlib",
    "scipy",
    "sklearn",
    "pandas",
    "cv2",
    "opencv",
    "tensorflow",
    "tensorboard",
]

# ---------------------------------------------------------------------------
# Analysis
# ---------------------------------------------------------------------------

a = Analysis(
    [_ENTRY_SCRIPT],
    pathex=[str(SRC)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excludes,
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="jp-anki-build",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,
    icon=str(ROOT / "packaging" / "icon.ico") if (ROOT / "packaging" / "icon.ico").exists() else None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="jp-anki-build",
)
