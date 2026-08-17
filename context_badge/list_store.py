"""Per-tab todo lists with the same dual-backup JSON writes as dwell data."""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any

from .dwell_store import load_json_with_backup, write_json_atomic
from .surface import editor_parts

BASE_LIST_KEY = "__base__"


def list_key(executable: str, surface: str) -> str:
    """Return the stable storage key for a foreground tab/page.

    Editor titles of the form ``file - workspace`` collapse to the workspace
    so file hops in the same repo share one list.
    """
    exe = (executable or "").strip() or "application"
    label = (surface or "").strip() or "Untitled window"
    parts = editor_parts(exe, label)
    if parts is not None:
        label = parts[1]
    return f"{exe}|{label}"


def split_list_key(key: str) -> tuple[str, str]:
    executable, separator, surface = key.partition("|")
    if not separator:
        return executable or "application", "Untitled window"
    return executable or "application", surface or "Untitled window"


def _merge_items(
    first: list[dict[str, Any]], second: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    seen = {str(item.get("id") or "") for item in first}
    merged = [dict(item) for item in first]
    for item in second:
        item_id = str(item.get("id") or "")
        if not item_id or item_id in seen:
            continue
        seen.add(item_id)
        merged.append(dict(item))
    return merged


def _collapse_editor_keys(
    lists: dict[str, list[dict[str, Any]]],
    notes: dict[str, str],
    labels: dict[str, str],
) -> tuple[
    dict[str, list[dict[str, Any]]],
    dict[str, str],
    dict[str, str],
    bool,
]:
    """Rewrite old editor keys ``exe|file - workspace`` to ``exe|workspace``."""
    changed = False
    for key in list(set(lists) | set(notes) | set(labels)):
        executable, surface = split_list_key(key)
        parts = editor_parts(executable, surface)
        if parts is None:
            continue
        canonical = list_key(executable, parts[1])
        if canonical == key:
            continue
        changed = True
        if key in lists:
            lists[canonical] = _merge_items(
                lists.get(canonical, []), lists.pop(key)
            )
            if not lists[canonical]:
                lists.pop(canonical, None)
        if key in notes:
            if canonical not in notes:
                notes[canonical] = notes[key]
            notes.pop(key, None)
        if key in labels:
            if canonical not in labels:
                labels[canonical] = labels[key]
            labels.pop(key, None)
        elif canonical not in labels:
            labels[canonical] = parts[1]
    return lists, notes, labels, changed


def next_row_after_enter(items: list[dict[str, Any]], item_id: str) -> str | None:
    """Return the id to insert a blank row after, or None for the trailing empty row."""
    if not item_id or not items or items[-1]["id"] == item_id:
        return None
    if any(item["id"] == item_id for item in items):
        return item_id
    return None


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
        self._lists, self._notes, self._labels, changed = self._load_lists()
        if changed:
            self._save()

    def _load_lists(
        self,
    ) -> tuple[
        dict[str, list[dict[str, Any]]],
        dict[str, str],
        dict[str, str],
        bool,
    ]:
        data = load_json_with_backup(self.path)
        if not data:
            return {}, {}, {}, False
        raw_lists = data.get("lists")
        if not isinstance(raw_lists, dict):
            return {}, {}, {}, False
        cleaned: dict[str, list[dict[str, Any]]] = {}
        notes: dict[str, str] = {}
        labels: dict[str, str] = {}
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
            label = str(bucket.get("label") or "").strip()
            if label:
                labels[key] = label
        cleaned, notes, labels, changed = _collapse_editor_keys(
            cleaned, notes, labels
        )
        return cleaned, notes, labels, changed

    def items(self, key: str) -> list[dict[str, Any]]:
        stored = self._lists.get(key, [])
        return [dict(item) for item in stored]

    def note(self, key: str) -> str:
        return self._notes.get(key, "")

    def label(self, key: str) -> str:
        return self._labels.get(key, "")

    def ensure_label(self, key: str, text: str) -> None:
        """Record a visible name the first time a list has one, without renaming."""
        label = str(text or "").strip()
        if not label or key in self._labels:
            return
        self._labels[key] = label
        if key in self._lists or key in self._notes:
            self._save()

    def set_note(self, key: str, text: str) -> None:
        note = str(text).strip()
        if note:
            self._notes[key] = note
        else:
            self._notes.pop(key, None)
        self._save()

    def open_count(self, key: str) -> int:
        return sum(1 for item in self._lists.get(key, []) if not item["done"])

    def add_item(
        self,
        key: str,
        text: str = "",
        *,
        after_id: str | None = None,
    ) -> dict[str, Any]:
        item = {"id": uuid.uuid4().hex, "text": str(text), "done": False}
        bucket = self._lists.setdefault(key, [])
        if after_id:
            for index, existing in enumerate(bucket):
                if existing["id"] == after_id:
                    bucket.insert(index + 1, item)
                    break
            else:
                bucket.append(item)
        else:
            bucket.append(item)
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
        kept_labels: dict[str, str] = {}
        for key in set(self._lists) | set(self._notes) | set(self._labels):
            nonempty = [
                dict(item)
                for item in self._lists.get(key, [])
                if str(item.get("id") or "")
            ]
            note = str(self._notes.get(key) or "").strip()
            label = str(self._labels.get(key) or "").strip()
            if not nonempty and not note:
                continue
            if nonempty:
                kept[key] = nonempty
            if note:
                kept_notes[key] = note
            if label:
                kept_labels[key] = label
            bucket: dict[str, Any] = {"items": nonempty}
            if note:
                bucket["note"] = note
            if label:
                bucket["label"] = label
            payload_lists[key] = bucket
        self._lists = kept
        self._notes = kept_notes
        self._labels = kept_labels
        if not payload_lists and not self.path.exists():
            return
        write_json_atomic(self.path, {"version": 1, "lists": payload_lists})
