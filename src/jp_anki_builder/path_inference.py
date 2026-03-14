"""Infer --source and --run-id from the images path.

Convention: the last two meaningful directory components of the images
path are used as source and run_id respectively.

Examples:
    ./screenshots/Miharu/Prologue     -> source=Miharu, run_id=Prologue
    ./screenshots/Miharu/Prologue/    -> source=Miharu, run_id=Prologue
    C:/imgs/GameX/Ch01                -> source=GameX, run_id=Ch01
    ./screenshots/single_folder       -> source=single_folder, run_id=single_folder
    ./screenshot.png                  -> None, None (single file, can't infer)
"""
from __future__ import annotations

from pathlib import Path


def infer_source_and_run_id(images_path: str) -> tuple[str | None, str | None]:
    """Infer source and run_id from the images path.

    Returns (source, run_id) or (None, None) if inference isn't possible.
    """
    p = Path(images_path).resolve()

    if p.is_file():
        # Single file: use parent directory structure
        p = p.parent

    parts = p.parts
    if len(parts) >= 2:
        return parts[-2], parts[-1]
    if len(parts) == 1:
        return parts[-1], parts[-1]
    return None, None
