import unittest
from datetime import datetime, timedelta, timezone
from typing import Any

from context_badge.dwell import DwellObservation, DwellTracker


class MemoryStore:
    def __init__(self, active: dict[str, Any] | None = None) -> None:
        self.active = dict(active) if active else None
        self.log: list[dict[str, Any]] = []

    def load_active(self) -> dict[str, Any] | None:
        return dict(self.active) if self.active else None

    def save_active(self, session: dict[str, Any] | None) -> None:
        self.active = None if session is None else dict(session)

    def append_session(self, session: dict[str, Any]) -> None:
        self.log.append(dict(session))
        self.active = None


class FakeClock:
    def __init__(self) -> None:
        self.mono = 1_000.0
        self.wall = datetime(2026, 8, 16, 17, 0, tzinfo=timezone.utc)

    def monotonic(self) -> float:
        return self.mono

    def now(self) -> datetime:
        return self.wall

    def advance(self, seconds: float) -> None:
        self.mono += seconds
        self.wall += timedelta(seconds=seconds)


def chrome(title: str = "Dwell tracking · GitHub - Google Chrome") -> DwellObservation:
    return DwellObservation("chrome.exe", "Google Chrome", title)


class DwellTrackerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.clock = FakeClock()
        self.store = MemoryStore()
        self.tracker = DwellTracker(
            self.store,
            noise_seconds=8,
            checkpoint_seconds=60,
            monotonic=self.clock.monotonic,
            wall_clock=self.clock.now,
        )

    def test_stays_shorter_than_noise_are_not_recorded(self) -> None:
        page = chrome()
        self.tracker.observe(page)
        self.clock.advance(7)
        self.tracker.observe(page)
        self.tracker.close()
        self.assertIsNone(self.store.active)
        self.assertEqual(self.store.log, [])

    def test_crossing_noise_writes_the_active_session(self) -> None:
        page = chrome()
        self.tracker.observe(page)
        self.clock.advance(8)
        self.tracker.observe(page)
        self.assertIsNotNone(self.store.active)
        assert self.store.active is not None
        self.assertGreaterEqual(self.store.active["duration_ms"], 8000)
        self.assertEqual(self.store.active["surface"], "Dwell tracking · GitHub")
        self.assertEqual(self.store.log, [])

    def test_checkpoint_updates_duration_after_t2(self) -> None:
        page = chrome()
        self.tracker.observe(page)
        self.clock.advance(8)
        self.tracker.observe(page)
        first = self.store.active["duration_ms"]
        self.clock.advance(51)
        self.tracker.observe(page)
        self.assertEqual(self.store.active["duration_ms"], first)
        self.clock.advance(1)
        self.tracker.observe(page)
        self.assertGreaterEqual(self.store.active["duration_ms"], 60_000)

    def test_page_switch_finalizes_a_recorded_stay(self) -> None:
        first = chrome()
        second = chrome("Python docs - Google Chrome")
        self.tracker.observe(first)
        self.clock.advance(12)
        self.tracker.observe(first)
        self.tracker.observe(second)
        self.assertEqual(len(self.store.log), 1)
        self.assertEqual(self.store.log[0]["close_reason"], "switch")
        self.assertEqual(self.store.log[0]["surface"], "Dwell tracking · GitHub")
        self.assertIsNone(self.store.active)

    def test_crash_recovery_keeps_sessions_past_noise(self) -> None:
        store = MemoryStore(
            {
                "id": "abc",
                "executable": "chrome.exe",
                "app": "Google Chrome",
                "title": "GitHub - Google Chrome",
                "surface": "GitHub",
                "started_at": "2026-08-16T17:00:00+00:00",
                "updated_at": "2026-08-16T17:01:00+00:00",
                "duration_ms": 20_000,
            }
        )
        DwellTracker(store, noise_seconds=8, checkpoint_seconds=60)
        self.assertEqual(len(store.log), 1)
        self.assertEqual(store.log[0]["close_reason"], "crash")
        self.assertIsNone(store.active)

    def test_crash_recovery_discards_noise(self) -> None:
        store = MemoryStore({"id": "abc", "duration_ms": 3_000})
        DwellTracker(store, noise_seconds=8, checkpoint_seconds=60)
        self.assertEqual(store.log, [])
        self.assertIsNone(store.active)


if __name__ == "__main__":
    unittest.main()
