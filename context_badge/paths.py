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


def dwell_index_path() -> Path:
    """Return the optional day-offset index beside the dwell log."""
    if is_frozen():
        return _runtime_dir() / "dwell-index.json"
    return _runtime_dir() / ".context-badge-dwell-index.json"


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


def local_pets_dir() -> Path:
    """Pets shipped with the app or dropped next to preferences."""
    return _runtime_dir() / "pets"


def codex_pets_dir() -> Path:
    """Codex custom pets live under the user profile."""
    return Path.home() / ".codex" / "pets"


def pet_search_dirs() -> tuple[Path, ...]:
    """Local pets first, then the shared Codex pet folder."""
    return (local_pets_dir(), codex_pets_dir())


def find_pet_folder(pet_id: str) -> Path | None:
    """Return the folder that contains ``pet.json`` for ``pet_id``."""
    name = str(pet_id or "").strip()
    if not name:
        return None
    for root in pet_search_dirs():
        folder = root / name
        if (folder / "pet.json").is_file():
            return folder
    return None
