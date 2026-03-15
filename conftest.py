from __future__ import annotations

import os
from pathlib import Path


def pytest_configure(config: object) -> None:
    """Redirect pytest's temp root to a local directory.

    On Windows, pytest-of-<user> in the system temp dir is sometimes owned by
    a different account and returns PermissionError when scanned.  Setting
    PYTEST_DEBUG_TEMPROOT to a project-local path avoids this entirely.
    """
    local_tmp = Path(__file__).parent / ".pytest_tmp"
    local_tmp.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("PYTEST_DEBUG_TEMPROOT", str(local_tmp.resolve()))
