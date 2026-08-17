import json
import tempfile
import unittest
from pathlib import Path

from context_badge.dwell_store import backup_path
from context_badge.list_store import (
    BASE_LIST_KEY,
    ListStore,
    list_key,
    next_row_after_enter,
    split_list_key,
)
from context_badge.surface import surface_label


class ListStoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "lists.json"
        self.store = ListStore(self.path)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_key_uses_executable_and_surface(self) -> None:
        surface = surface_label("chrome.exe", "GitHub - Google Chrome")
        key = list_key("chrome.exe", surface)
        self.assertEqual(key, "chrome.exe|GitHub")
        self.assertEqual(split_list_key(key), ("chrome.exe", "GitHub"))

    def test_editor_key_collapses_file_to_workspace(self) -> None:
        self.assertEqual(
            list_key("Cursor.exe", "docs/dev-log.md - context-badge"),
            "Cursor.exe|context-badge",
        )
        self.assertEqual(
            list_key("Cursor.exe", "context-badge"),
            "Cursor.exe|context-badge",
        )

    def test_key_keeps_pipes_in_the_surface(self) -> None:
        key = list_key("code.exe", "a|b")
        self.assertEqual(split_list_key(key), ("code.exe", "a|b"))

    def test_empty_list_is_not_written(self) -> None:
        key = list_key("chrome.exe", "GitHub")
        self.assertEqual(self.store.items(key), [])
        self.store._save()
        self.assertFalse(self.path.exists())

    def test_crud_round_trip(self) -> None:
        key = list_key("chrome.exe", "GitHub")
        created = self.store.add_item(key, "Review PR")
        self.store.add_item(key, "Ship it")
        self.store.set_done(key, created["id"], True)
        self.store.set_text(key, created["id"], "Review the PR")
        items = self.store.items(key)
        self.assertEqual(len(items), 2)
        self.assertEqual(items[0]["text"], "Review the PR")
        self.assertTrue(items[0]["done"])
        self.assertEqual(self.store.open_count(key), 1)
        self.store.delete_item(key, items[1]["id"])
        self.assertEqual(len(self.store.items(key)), 1)

    def test_note_round_trip_and_survives_without_items(self) -> None:
        key = list_key("chrome.exe", "GitHub")
        self.store.set_note(key, "  ship after lunch  ")
        self.assertEqual(self.store.note(key), "ship after lunch")
        payload = json.loads(self.path.read_text(encoding="utf-8"))
        self.assertEqual(payload["lists"][key]["note"], "ship after lunch")
        self.assertEqual(payload["lists"][key]["items"], [])
        restored = ListStore(self.path)
        self.assertEqual(restored.note(key), "ship after lunch")
        self.assertEqual(restored.items(key), [])

    def test_deleting_the_last_item_keeps_the_key_when_a_note_exists(self) -> None:
        key = list_key("notepad.exe", "notes.txt")
        self.store.set_note(key, "keep this")
        item = self.store.add_item(key, "one")
        self.store.delete_item(key, item["id"])
        payload = json.loads(self.path.read_text(encoding="utf-8"))
        self.assertEqual(payload["lists"][key]["items"], [])
        self.assertEqual(payload["lists"][key]["note"], "keep this")

    def test_blank_note_is_dropped(self) -> None:
        key = list_key("chrome.exe", "GitHub")
        self.store.set_note(key, "temp")
        self.store.set_note(key, "   ")
        payload = json.loads(self.path.read_text(encoding="utf-8"))
        self.assertEqual(payload["lists"], {})

    def test_deleting_the_last_item_drops_the_key(self) -> None:
        key = list_key("notepad.exe", "notes.txt")
        item = self.store.add_item(key, "one")
        self.store.delete_item(key, item["id"])
        payload = json.loads(self.path.read_text(encoding="utf-8"))
        self.assertEqual(payload["lists"], {})

    def test_base_key_does_not_collide_with_window_keys(self) -> None:
        self.assertNotIn("|", BASE_LIST_KEY)
        self.assertIn("|", list_key("chrome.exe", "Base"))
        self.assertNotEqual(BASE_LIST_KEY, list_key("chrome.exe", BASE_LIST_KEY))

    def test_base_list_is_independent_of_window_keys(self) -> None:
        window = list_key("chrome.exe", "GitHub")
        self.store.add_item(BASE_LIST_KEY, "inbox")
        self.store.add_item(window, "review")
        self.assertEqual(
            [item["text"] for item in self.store.items(BASE_LIST_KEY)],
            ["inbox"],
        )
        self.assertEqual(
            [item["text"] for item in self.store.items(window)],
            ["review"],
        )
        payload = json.loads(self.path.read_text(encoding="utf-8"))
        self.assertIn(BASE_LIST_KEY, payload["lists"])
        self.assertIn(window, payload["lists"])

    def test_add_item_after_id_inserts_in_the_middle(self) -> None:
        key = list_key("chrome.exe", "GitHub")
        first = self.store.add_item(key, "one")
        self.store.add_item(key, "three")
        self.store.add_item(key, "two", after_id=first["id"])
        self.assertEqual(
            [item["text"] for item in self.store.items(key)],
            ["one", "two", "three"],
        )

    def test_add_item_after_unknown_id_appends(self) -> None:
        key = list_key("chrome.exe", "GitHub")
        self.store.add_item(key, "one")
        self.store.add_item(key, "two", after_id="missing")
        self.assertEqual(
            [item["text"] for item in self.store.items(key)],
            ["one", "two"],
        )

    def test_next_row_after_enter_inserts_in_the_middle(self) -> None:
        items = [
            {"id": "a", "text": "one", "done": False},
            {"id": "b", "text": "two", "done": False},
            {"id": "c", "text": "three", "done": False},
        ]
        self.assertEqual(next_row_after_enter(items, "a"), "a")
        self.assertEqual(next_row_after_enter(items, "b"), "b")
        self.assertIsNone(next_row_after_enter(items, "c"))
        self.assertIsNone(next_row_after_enter(items, "missing"))
        self.assertIsNone(next_row_after_enter([], "a"))

    def test_corrupt_file_falls_back_to_backup(self) -> None:
        key = list_key("chrome.exe", "GitHub")
        first = self.store.add_item(key, "kept")
        self.store.add_item(key, "newer")
        self.path.write_text("{not json", encoding="utf-8")
        restored = ListStore(self.path)
        items = restored.items(key)
        self.assertEqual([item["id"] for item in items], [first["id"]])
        bak = json.loads(backup_path(self.path).read_text(encoding="utf-8"))
        self.assertEqual(bak["lists"][key]["items"][0]["text"], "kept")

    def test_label_is_stored_once_and_not_overwritten(self) -> None:
        key = list_key("Cursor.exe", "context-badge")
        self.store.add_item(key, "one")
        self.store.ensure_label(key, "context-badge")
        self.store.ensure_label(key, "other-name")
        self.assertEqual(self.store.label(key), "context-badge")
        payload = json.loads(self.path.read_text(encoding="utf-8"))
        self.assertEqual(payload["lists"][key]["label"], "context-badge")

    def test_old_editor_file_keys_migrate_to_workspace(self) -> None:
        old = "Cursor.exe|docs/dev-log.md - context-badge"
        workspace = list_key("Cursor.exe", "context-badge")
        self.path.write_text(
            json.dumps(
                {
                    "version": 1,
                    "lists": {
                        old: {
                            "items": [
                                {"id": "a", "text": "from file key", "done": False}
                            ],
                            "note": "workspace note",
                        },
                        workspace: {
                            "items": [
                                {"id": "b", "text": "already workspace", "done": False}
                            ],
                            "label": "context-badge",
                        },
                    },
                }
            ),
            encoding="utf-8",
        )
        store = ListStore(self.path)
        texts = [item["text"] for item in store.items(workspace)]
        self.assertEqual(texts, ["already workspace", "from file key"])
        self.assertEqual(store.note(workspace), "workspace note")
        self.assertEqual(store.label(workspace), "context-badge")
        payload = json.loads(self.path.read_text(encoding="utf-8"))
        self.assertNotIn(old, payload["lists"])
        self.assertEqual(payload["lists"][workspace]["label"], "context-badge")


if __name__ == "__main__":
    unittest.main()
