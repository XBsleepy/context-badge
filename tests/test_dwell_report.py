import unittest
from datetime import date, timezone

from context_badge.dwell_report import (
    aggregate_by_app,
    clip_session,
    day_range,
    format_duration,
    merge_adjacent_by_app,
    slices_for_day,
)


TZ = timezone.utc


def session(
    app: str,
    start: str,
    end: str,
    surface: str = "",
) -> dict:
    return {
        "app": app,
        "surface": surface or app,
        "title": surface or app,
        "started_at": start,
        "ended_at": end,
        "duration_ms": 0,
    }


class DwellReportTests(unittest.TestCase):
    def test_format_duration_uses_compact_units(self) -> None:
        self.assertEqual(format_duration(45_000), "45s")
        self.assertEqual(format_duration(12 * 60_000), "12m")
        self.assertEqual(format_duration(90 * 60_000), "1h 30m")

    def test_aggregate_by_app_sums_and_sorts(self) -> None:
        records = [
            session("Chrome", "2026-08-16T10:00:00+00:00", "2026-08-16T10:10:00+00:00"),
            session("Code", "2026-08-16T10:10:00+00:00", "2026-08-16T10:40:00+00:00"),
            session("Chrome", "2026-08-16T10:40:00+00:00", "2026-08-16T10:50:00+00:00"),
        ]
        slices = slices_for_day(records, date(2026, 8, 16), tzinfo=TZ)
        totals = aggregate_by_app(slices)
        self.assertEqual([item.app for item in totals], ["Code", "Chrome"])
        self.assertEqual(totals[0].duration_ms, 30 * 60_000)
        self.assertEqual(totals[1].duration_ms, 20 * 60_000)
        self.assertEqual(totals[1].count, 2)

    def test_midnight_session_is_clipped_to_each_day(self) -> None:
        records = [
            session(
                "Chrome",
                "2026-08-16T23:50:00+00:00",
                "2026-08-17T00:20:00+00:00",
            )
        ]
        first = slices_for_day(records, date(2026, 8, 16), tzinfo=TZ)
        second = slices_for_day(records, date(2026, 8, 17), tzinfo=TZ)
        self.assertEqual(len(first), 1)
        self.assertEqual(len(second), 1)
        self.assertEqual(first[0].duration_ms, 10 * 60_000)
        self.assertEqual(second[0].duration_ms, 20 * 60_000)

    def test_other_days_are_excluded(self) -> None:
        records = [
            session("Chrome", "2026-08-15T10:00:00+00:00", "2026-08-15T11:00:00+00:00")
        ]
        self.assertEqual(slices_for_day(records, date(2026, 8, 16), tzinfo=TZ), [])

    def test_ribbon_merges_consecutive_same_app_slices(self) -> None:
        records = [
            session(
                "Chrome",
                "2026-08-16T10:00:00+00:00",
                "2026-08-16T10:01:00+00:00",
                "Tab A",
            ),
            session(
                "Chrome",
                "2026-08-16T10:01:00+00:00",
                "2026-08-16T10:02:00+00:00",
                "Tab B",
            ),
            session(
                "Code",
                "2026-08-16T10:02:00+00:00",
                "2026-08-16T10:03:00+00:00",
            ),
        ]
        slices = slices_for_day(records, date(2026, 8, 16), tzinfo=TZ)
        merged = merge_adjacent_by_app(slices)
        self.assertEqual(len(slices), 3)
        self.assertEqual(len(merged), 2)
        self.assertEqual(merged[0].app, "Chrome")
        self.assertEqual(merged[0].duration_ms, 2 * 60_000)

    def test_clip_rejects_unparseable_sessions(self) -> None:
        start, end = day_range(date(2026, 8, 16), tzinfo=TZ)
        self.assertIsNone(clip_session({"started_at": "nope"}, start, end))


if __name__ == "__main__":
    unittest.main()
