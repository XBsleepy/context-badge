"""Per-tab todo lists with the same dual-backup JSON writes as dwell data."""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any

from .dwell_store import load_json_with_backup, write_json_atomic


def list_key(executable: str, surface: str) -> str:
    """Return the stable storage key for a foreground tab/page."""
    exe = (executable or "").strip() or "application"
    label = (surface or "").strip() or "Untitled window"
    return f"{exe}|{label}"


def split_list_key(key: str) -> tuple[str, str]:
    executable, separator, surface = key.partition("|")
    if not separator:
        return executable or "application", "Untitled window"
    return executable or "application", surface or "Untitled window"


def _clean_item(raw: object) -> dict[str, Any] | None:
    if not isinstance(raw, dict):
        return None
    item_id = str(raw.get("id") or "").strip()
    if not item_id:
        return None
    return {
        "id": item_id,
        "text": str(raw.get("text") or ""),
        "done": bool(raw.get("done")),
    }


class ListStore:
    """Load and save todo items keyed by executable plus surface label."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._lists, self._notes = self._load_lists()

    def _load_lists(
        self,
    ) -> tuple[dict[str, list[dict[str, Any]]], dict[str, str]]:
        data = load_json_with_backup(self.path)
        if not data:
            return {}, {}
        raw_lists = data.get("lists")
        if not isinstance(raw_lists, dict):
            return {}, {}
        cleaned: dict[str, list[dict[str, Any]]] = {}
        notes: dict[str, str] = {}
        for key, bucket in raw_lists.items():
            if not isinstance(key, str) or not isinstance(bucket, dict):
                continue
            items = [
                item
                for item in (_clean_item(raw) for raw in bucket.get("items", []))
                if item is not None
            ]
            if items:
                cleaned[key] = items
            note = str(bucket.get("note") or "").strip()
            if note:
                notes[key] = note
        return cleaned, notes

    def items(self, key: str) -> list[dict[str, Any]]:
        stored = self._lists.get(key, [])
        return [dict(item) for item in stored]

    def note(self, key: str) -> str:
        return self._notes.get(key, "")

    def set_note(self, key: str, text: str) -> None:
        note = str(text).strip()
        if note:
            self._notes[key] = note
        else:
            self._notes.pop(key, None)
        self._save()

    def open_count(self, key: str) -> int:
        return sum(1 for item in self._lists.get(key, []) if not item["done"])

    def add_item(self, key: str, text: str = "") -> dict[str, Any]:
        item = {"id": uuid.uuid4().hex, "text": str(text), "done": False}
        self._lists.setdefault(key, []).append(item)
        self._save()
        return dict(item)

    def set_text(self, key: str, item_id: str, text: str) -> None:
        item = self._find(key, item_id)
        if item is None:
            return
        item["text"] = str(text)
        self._save()

    def set_done(self, key: str, item_id: str, done: bool) -> None:
        item = self._find(key, item_id)
        if item is None:
            return
        item["done"] = bool(done)
        self._save()

    def delete_item(self, key: str, item_id: str) -> None:
        items = self._lists.get(key)
        if not items:
            return
        self._lists[key] = [item for item in items if item["id"] != item_id]
        self._save()

    def _find(self, key: str, item_id: str) -> dict[str, Any] | None:
        for item in self._lists.get(key, []):
            if item["id"] == item_id:
                return item
        return None

    def _save(self) -> None:
        payload_lists: dict[str, dict[str, Any]] = {}
        kept: dict[str, list[dict[str, Any]]] = {}
        kept_notes: dict[str, str] = {}
        for key in set(self._lists) | set(self._notes):
            nonempty = [
                dict(item)
                for item in self._lists.get(key, [])
                if str(item.get("id") or "")
            ]
            note = str(self._notes.get(key) or "").strip()
            if not nonempty and not note:
                continue
            if nonempty:
                kept[key] = nonempty
            if note:
                kept_notes[key] = note
            bucket: dict[str, Any] = {"items": nonempty}
            if note:
                bucket["note"] = note
            payload_lists[key] = bucket
        self._lists = kept
        self._notes = kept_notes
        if not payload_lists and not self.path.exists():
            return
        write_json_atomic(self.path, {"version": 1, "lists": payload_lists})
