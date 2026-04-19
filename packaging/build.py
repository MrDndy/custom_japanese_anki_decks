"""Build script for creating a Windows distributable with PyInstaller.

Usage:
    python packaging/build.py

Produces: dist/jp-anki-build/  (directory distribution)
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SPEC_FILE = Path(__file__).resolve().parent / "jp_anki_builder.spec"


def main() -> None:
    os.chdir(ROOT)

    if not SPEC_FILE.exists():
        print(f"[ERROR] Spec file not found: {SPEC_FILE}")
        sys.exit(1)

    cmd = [
        sys.executable,
        "-m",
        "PyInstaller",
        str(SPEC_FILE),
        "--noconfirm",
        "--clean",
    ]
    print(f"[BUILD] Running: {' '.join(cmd)}")
    result = subprocess.run(cmd)
    if result.returncode != 0:
        print("[ERROR] PyInstaller build failed.")
        sys.exit(result.returncode)

    dist_dir = ROOT / "dist" / "jp-anki-build"
    if dist_dir.exists():
        print(f"\n[OK] Build complete: {dist_dir}")
        print("     Test with:")
        print(f'       "{dist_dir / "jp-anki-build.exe"}" --help')
        print(f'       "{dist_dir / "jp-anki-build.exe"}" gui')
    else:
        print("[WARN] dist/jp-anki-build/ not found — check build output above.")


if __name__ == "__main__":
    main()
