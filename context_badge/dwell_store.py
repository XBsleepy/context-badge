"""Crash-tolerant dwell persistence using JSON and JSONL dual backups."""

from __future__ import annotations

import json
import os
import shutil
from datetime import date, datetime, timedelta
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


def _read_jsonl_bytes(path: Path, start: int, end: int) -> list[dict[str, Any]]:
    """Read JSONL lines whose byte offsets fall in ``[start, end)``."""
    if end <= start:
        return []
    try:
        with path.open("rb") as handle:
            handle.seek(max(0, int(start)))
            raw = handle.read(max(0, int(end) - max(0, int(start))))
    except OSError:
        return []
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        text = raw.decode("utf-8", errors="replace")
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


def append_jsonl(path: Path, record: dict[str, Any]) -> int:
    """Append one JSONL record. Return the byte offset where the line starts."""
    path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(record, ensure_ascii=False, separators=(",", ":"))
    encoded = (line + "\n").encode("utf-8")
    try:
        offset = path.stat().st_size if path.exists() else 0
    except OSError:
        offset = 0
    with path.open("ab") as handle:
        handle.write(encoded)
        handle.flush()
        os.fsync(handle.fileno())
    _append_or_refresh_backup(path, encoded)
    return int(offset)


def _append_or_refresh_backup(path: Path, encoded: bytes) -> None:
    """Keep the backup in sync by appending when possible, else full copy."""
    bak = backup_path(path)
    try:
        primary_size = path.stat().st_size
    except OSError:
        return
    try:
        if not bak.exists():
            _copy_to_backup(path)
            return
        bak_size = bak.stat().st_size
        # Healthy bak trails primary by exactly this line.
        if bak_size + len(encoded) == primary_size:
            with bak.open("ab") as handle:
                handle.write(encoded)
                handle.flush()
                os.fsync(handle.fileno())
            return
        if bak_size == primary_size:
            return
    except OSError:
        pass
    _copy_to_backup(path)


def _day_key(day: date) -> str:
    return day.isoformat()


def _session_days(session: dict[str, Any]) -> list[date]:
    started = session.get("started_at")
    if not isinstance(started, str) or not started.strip():
        return []
    try:
        start = datetime.fromisoformat(started)
    except ValueError:
        return []
    if start.tzinfo is None:
        start = start.astimezone()
    end: datetime | None = None
    for key in ("ended_at", "updated_at"):
        raw = session.get(key)
        if not isinstance(raw, str) or not raw.strip():
            continue
        try:
            parsed = datetime.fromisoformat(raw)
        except ValueError:
            continue
        if parsed.tzinfo is None:
            parsed = parsed.astimezone()
        end = parsed
        break
    if end is None:
        try:
            duration_ms = int(session.get("duration_ms") or 0)
        except (TypeError, ValueError):
            duration_ms = 0
        end = start + timedelta(milliseconds=max(0, duration_ms))
    if end < start:
        end = start
    days: list[date] = []
    cursor = start.astimezone().date()
    last = end.astimezone().date()
    while cursor <= last:
        days.append(cursor)
        cursor += timedelta(days=1)
    return days

class DwellStore:
    """Persist the open dwell and completed history with dual backups."""

    def __init__(
        self,
        log_path: Path,
        active_path: Path,
        *,
        index_path: Path | None = None,
    ) -> None:
        self.log_path = log_path
        self.active_path = active_path
        self.index_path = index_path or log_path.with_name(
            log_path.name.replace(".jsonl", "") + "-index.json"
            if log_path.name.endswith(".jsonl")
            else log_path.name + "-index.json"
        )

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
        offset = append_jsonl(self.log_path, session)
        try:
            size = self.log_path.stat().st_size
        except OSError:
            size = offset
        self._index_extend(session, offset, size)
        self.save_active(None)

    def load_history(self) -> list[dict[str, Any]]:
        return read_jsonl_with_backup(self.log_path)

    def load_history_for_day(self, day: date) -> list[dict[str, Any]]:
        """Load records that may touch ``day``. Falls back to a full scan."""
        data = self._load_index()
        rebuilt = False
        if data is None:
            data = self.rebuild_index()
            rebuilt = True
        days = data.get("days") if isinstance(data, dict) else None
        if not isinstance(days, dict):
            return self.load_history()
        entry = days.get(_day_key(day))
        if not isinstance(entry, dict):
            return []
        try:
            start = int(entry.get("start", 0))
            end = int(entry.get("end", 0))
        except (TypeError, ValueError):
            return self.load_history()
        records = _read_jsonl_bytes(self.log_path, start, end)
        if records or rebuilt or end <= start:
            return records
        data = self.rebuild_index()
        days = data.get("days") if isinstance(data, dict) else None
        if not isinstance(days, dict):
            return self.load_history()
        entry = days.get(_day_key(day))
        if not isinstance(entry, dict):
            return []
        try:
            start = int(entry.get("start", 0))
            end = int(entry.get("end", 0))
        except (TypeError, ValueError):
            return self.load_history()
        return _read_jsonl_bytes(self.log_path, start, end)
    def rebuild_index(self) -> dict[str, Any]:
        """Scan the log and rewrite the day-offset index."""
        days: dict[str, dict[str, int]] = {}
        try:
            size = self.log_path.stat().st_size
            mtime_ns = self.log_path.stat().st_mtime_ns
        except OSError:
            size = 0
            mtime_ns = 0
        if size and self.log_path.exists():
            offset = 0
            try:
                with self.log_path.open("rb") as handle:
                    while True:
                        line = handle.readline()
                        if not line:
                            break
                        next_offset = offset + len(line)
                        stripped = line.strip()
                        if stripped:
                            try:
                                item = json.loads(stripped.decode("utf-8"))
                            except (UnicodeDecodeError, json.JSONDecodeError):
                                item = None
                            if isinstance(item, dict):
                                for day in _session_days(item):
                                    key = _day_key(day)
                                    entry = days.get(key)
                                    if entry is None:
                                        days[key] = {"start": offset, "end": next_offset}
                                    else:
                                        entry["start"] = min(entry["start"], offset)
                                        entry["end"] = max(entry["end"], next_offset)
                        offset = next_offset
            except OSError:
                days = {}
        payload = {
            "version": 1,
            "log_size": size,
            "log_mtime_ns": mtime_ns,
            "days": days,
        }
        try:
            write_json_atomic(self.index_path, payload)
        except OSError:
            pass
        return payload

    def _load_index(self) -> dict[str, Any] | None:
        data = load_json_with_backup(self.index_path)
        if not data or int(data.get("version") or 0) != 1:
            return None
        try:
            size = self.log_path.stat().st_size if self.log_path.exists() else 0
        except OSError:
            return None
        if int(data.get("log_size") or -1) != size:
            return None
        days = data.get("days")
        if not isinstance(days, dict):
            return None
        return data

    def _index_extend(self, session: dict[str, Any], offset: int, end: int) -> None:
        data = self._load_index()
        if data is None:
            self.rebuild_index()
            return
        days = data.get("days")
        if not isinstance(days, dict):
            days = {}
            data["days"] = days
        touched = _session_days(session)
        if not touched:
            # Still keep size/mtime current so the index stays valid.
            pass
        for day in touched:
            key = _day_key(day)
            entry = days.get(key)
            if not isinstance(entry, dict):
                days[key] = {"start": offset, "end": end}
            else:
                try:
                    entry["start"] = min(int(entry.get("start", offset)), offset)
                    entry["end"] = max(int(entry.get("end", end)), end)
                except (TypeError, ValueError):
                    days[key] = {"start": offset, "end": end}
        try:
            data["log_size"] = self.log_path.stat().st_size
            data["log_mtime_ns"] = self.log_path.stat().st_mtime_ns
        except OSError:
            data["log_size"] = end
        try:
            write_json_atomic(self.index_path, data)
        except OSError:
            pass
