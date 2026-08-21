import json
import tempfile
import unittest
from datetime import date
from pathlib import Path

from context_badge.dwell_store import DwellStore, backup_path


class DwellStoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.dir = Path(self.temp.name)
        self.log_path = self.dir / "dwell.jsonl"
        self.active_path = self.dir / "dwell-active.json"
        self.index_path = self.dir / "dwell-index.json"
        self.store = DwellStore(
            self.log_path,
            self.active_path,
            index_path=self.index_path,
        )

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

    def test_append_extends_backup_without_full_rewrite(self) -> None:
        first = {
            "id": "a",
            "started_at": "2026-08-16T10:00:00+08:00",
            "ended_at": "2026-08-16T10:01:00+08:00",
            "duration_ms": 60_000,
        }
        self.store.append_session(first)
        bak_size = backup_path(self.log_path).stat().st_size
        second = {
            "id": "b",
            "started_at": "2026-08-16T11:00:00+08:00",
            "ended_at": "2026-08-16T11:01:00+08:00",
            "duration_ms": 60_000,
        }
        self.store.append_session(second)
        self.assertGreater(backup_path(self.log_path).stat().st_size, bak_size)
        self.assertEqual(
            [item["id"] for item in self.store.load_history()],
            ["a", "b"],
        )

    def test_day_index_loads_only_matching_day(self) -> None:
        day_a = date(2026, 8, 16)
        day_b = date(2026, 8, 17)
        self.store.append_session(
            {
                "id": "a",
                "app": "A",
                "started_at": "2026-08-16T10:00:00+08:00",
                "ended_at": "2026-08-16T10:05:00+08:00",
                "duration_ms": 300_000,
            }
        )
        self.store.append_session(
            {
                "id": "b",
                "app": "B",
                "started_at": "2026-08-17T10:00:00+08:00",
                "ended_at": "2026-08-17T10:05:00+08:00",
                "duration_ms": 300_000,
            }
        )
        self.assertEqual(
            [item["id"] for item in self.store.load_history_for_day(day_a)],
            ["a"],
        )
        self.assertEqual(
            [item["id"] for item in self.store.load_history_for_day(day_b)],
            ["b"],
        )
        self.assertTrue(self.index_path.is_file())

    def test_missing_index_rebuilds_on_demand(self) -> None:
        self.store.append_session(
            {
                "id": "solo",
                "started_at": "2026-08-18T12:00:00+08:00",
                "ended_at": "2026-08-18T12:01:00+08:00",
                "duration_ms": 60_000,
            }
        )
        self.index_path.unlink()
        records = self.store.load_history_for_day(date(2026, 8, 18))
        self.assertEqual([item["id"] for item in records], ["solo"])
        self.assertTrue(self.index_path.is_file())


if __name__ == "__main__":
    unittest.main()
