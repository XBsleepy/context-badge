"""Filesystem locations used by Context Badge."""

from __future__ import annotations

import os
import sys
from pathlib import Path


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def _runtime_dir() -> Path:
    if is_frozen():
        appdata = os.environ.get("LOCALAPPDATA")
        base = Path(appdata) if appdata else Path.home() / "AppData" / "Local"
        return base / "Context Badge"
    return Path(__file__).resolve().parents[1]


def config_path() -> Path:
    """Return the preferences file for the current runtime.

    Source checkouts keep ``.context-badge.json`` beside the repository.
    The packaged Windows executable stores the same settings under
    ``%LOCALAPPDATA%\\Context Badge`` so they survive temp extraction.
    """
    if is_frozen():
        return _runtime_dir() / "preferences.json"
    return _runtime_dir() / ".context-badge.json"


def dwell_log_path() -> Path:
    """Return the append-only dwell history file."""
    if is_frozen():
        return _runtime_dir() / "dwell.jsonl"
    return _runtime_dir() / ".context-badge-dwell.jsonl"


def dwell_active_path() -> Path:
    """Return the in-progress dwell session file."""
    if is_frozen():
        return _runtime_dir() / "dwell-active.json"
    return _runtime_dir() / ".context-badge-dwell-active.json"


def lists_path() -> Path:
    """Return the per-tab todo list file."""
    if is_frozen():
        return _runtime_dir() / "lists.json"
    return _runtime_dir() / ".context-badge-lists.json"
