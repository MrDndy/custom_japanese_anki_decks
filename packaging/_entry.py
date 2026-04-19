"""PyInstaller entry point for jp-anki-build CLI."""
import os
import sys

# Force UTF-8 output on Windows consoles to avoid UnicodeEncodeError
if sys.platform == "win32":
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# Ensure src/ is on the path for editable installs
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from jp_anki_builder.cli import app  # noqa: E402

app()
