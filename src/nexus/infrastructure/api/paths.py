"""Filesystem locations shared by the API layer.

The NEXUS backend can serve (and write state for) the HOLO frontend that
ships in this repository. `frontend_dir()` resolves the `frontend/` folder:
the ``NEXUS_FRONTEND_DIR`` env var wins, then the repo checkout layout
(``<repo>/frontend``), then a ``frontend`` directory relative to the CWD.
"""

from __future__ import annotations

import os
from pathlib import Path


def frontend_dir() -> Path | None:
    """Return the frontend directory if it exists, else ``None``."""
    env = os.getenv("NEXUS_FRONTEND_DIR", "").strip()
    candidates = []
    if env:
        candidates.append(Path(env).expanduser())
    candidates.append(Path(__file__).resolve().parents[4] / "frontend")
    candidates.append(Path("frontend"))
    for c in candidates:
        try:
            if c.is_dir():
                return c
        except OSError:
            continue
    return None
