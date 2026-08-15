"""Filesystem locations used by Context Badge."""

from __future__ import annotations

import os
import sys
from pathlib import Path


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def config_path() -> Path:
    """Return the preferences file for the current runtime.

    Source checkouts keep ``.context-badge.json`` beside the repository.
    The packaged Windows executable stores the same settings under
    ``%LOCALAPPDATA%\\Context Badge`` so they survive temp extraction.
    """
    if is_frozen():
        appdata = os.environ.get("LOCALAPPDATA")
        base = Path(appdata) if appdata else Path.home() / "AppData" / "Local"
        return base / "Context Badge" / "preferences.json"
    return Path(__file__).resolve().parents[1] / ".context-badge.json"
