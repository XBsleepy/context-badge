import json
import tempfile
import unittest
from pathlib import Path

from context_badge.dwell_store import backup_path
from context_badge.list_store import ListStore, list_key, split_list_key
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

    def test_deleting_the_last_item_drops_the_key(self) -> None:
        key = list_key("notepad.exe", "notes.txt")
        item = self.store.add_item(key, "one")
        self.store.delete_item(key, item["id"])
        payload = json.loads(self.path.read_text(encoding="utf-8"))
        self.assertEqual(payload["lists"], {})

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


if __name__ == "__main__":
    unittest.main()
