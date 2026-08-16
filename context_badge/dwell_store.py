"""Crash-tolerant dwell persistence using JSON and JSONL dual backups."""

from __future__ import annotations

import json
import os
import shutil
from pathlib import Path
from typing import Any


def backup_path(path: Path) -> Path:
    return path.with_name(path.name + ".bak")


def _fsync_directory(path: Path) -> None:
    directory = str(path.parent)
    flags = os.O_RDONLY
    if hasattr(os, "O_DIRECTORY"):
        flags |= os.O_DIRECTORY
    try:
        fd = os.open(directory, flags)
    except OSError:
        return
    try:
        os.fsync(fd)
    except OSError:
        pass
    finally:
        os.close(fd)


def _copy_to_backup(path: Path) -> None:
    if not path.exists() or path.stat().st_size == 0:
        return
    bak = backup_path(path)
    tmp = bak.with_name(bak.name + ".tmp")
    shutil.copy2(path, tmp)
    os.replace(tmp, bak)
    _fsync_directory(bak)


def write_json_atomic(path: Path, payload: object) -> None:
    """Write JSON by rotating the last good file, then replacing atomically."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    encoded = json.dumps(payload, ensure_ascii=False, indent=2)
    with tmp.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(encoded)
        handle.flush()
        os.fsync(handle.fileno())
    if path.exists():
        try:
            json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError):
            pass
        else:
            _copy_to_backup(path)
    os.replace(tmp, path)
    _fsync_directory(path)


def load_json_with_backup(path: Path) -> dict[str, Any] | None:
    for candidate in (path, backup_path(path)):
        try:
            data = json.loads(candidate.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError):
            continue
        if isinstance(data, dict):
            return data
    return None


def read_jsonl_with_backup(path: Path) -> list[dict[str, Any]]:
    primary = _read_jsonl(path)
    if not _jsonl_looks_corrupt(path, primary):
        return primary
    backup = _read_jsonl(backup_path(path))
    return backup if backup else primary


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return []
    records: list[dict[str, Any]] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        try:
            item = json.loads(stripped)
        except json.JSONDecodeError:
            continue
        if isinstance(item, dict):
            records.append(item)
    return records


def _jsonl_looks_corrupt(path: Path, records: list[dict[str, Any]]) -> bool:
    try:
        size = path.stat().st_size
    except OSError:
        return True
    if size == 0:
        return False
    return not records


def append_jsonl(path: Path, record: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(record, ensure_ascii=False, separators=(",", ":"))
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(line)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    _copy_to_backup(path)


class DwellStore:
    """Persist the open dwell and completed history with dual backups."""

    def __init__(self, log_path: Path, active_path: Path) -> None:
        self.log_path = log_path
        self.active_path = active_path

    def load_active(self) -> dict[str, Any] | None:
        data = load_json_with_backup(self.active_path)
        if not data:
            return None
        session = data.get("session")
        return session if isinstance(session, dict) else None

    def save_active(self, session: dict[str, Any] | None) -> None:
        write_json_atomic(
            self.active_path,
            {"version": 1, "session": session},
        )

    def append_session(self, session: dict[str, Any]) -> None:
        append_jsonl(self.log_path, session)
        self.save_active(None)

    def load_history(self) -> list[dict[str, Any]]:
        return read_jsonl_with_backup(self.log_path)
