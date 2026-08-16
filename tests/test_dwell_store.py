import json
import tempfile
import unittest
from pathlib import Path

from context_badge.dwell_store import DwellStore, backup_path


class DwellStoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.dir = Path(self.temp.name)
        self.log_path = self.dir / "dwell.jsonl"
        self.active_path = self.dir / "dwell-active.json"
        self.store = DwellStore(self.log_path, self.active_path)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_active_round_trip_and_backup(self) -> None:
        session = {"id": "one", "duration_ms": 12_000}
        self.store.save_active(session)
        self.store.save_active({"id": "two", "duration_ms": 24_000})
        self.assertEqual(self.store.load_active()["id"], "two")
        bak = json.loads(backup_path(self.active_path).read_text(encoding="utf-8"))
        self.assertEqual(bak["session"]["id"], "one")

    def test_corrupt_active_falls_back_to_backup(self) -> None:
        self.store.save_active({"id": "good", "duration_ms": 9_000})
        self.store.save_active({"id": "newer", "duration_ms": 10_000})
        self.active_path.write_text("{not json", encoding="utf-8")
        loaded = self.store.load_active()
        self.assertEqual(loaded["id"], "good")

    def test_append_survives_a_truncated_last_line(self) -> None:
        self.store.append_session({"id": "keep", "duration_ms": 9_000})
        with self.log_path.open("a", encoding="utf-8") as handle:
            handle.write('{"id":"broken"')
        records = self.store.load_history()
        self.assertEqual(records, [{"id": "keep", "duration_ms": 9_000}])

    def test_corrupt_log_falls_back_to_backup(self) -> None:
        self.store.append_session({"id": "first", "duration_ms": 9_000})
        self.store.append_session({"id": "second", "duration_ms": 10_000})
        self.log_path.write_bytes(b"\xff\xfe totally broken")
        records = self.store.load_history()
        self.assertEqual([item["id"] for item in records], ["first", "second"])


if __name__ == "__main__":
    unittest.main()
