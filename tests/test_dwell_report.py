import unittest
from datetime import date, datetime, timedelta, timezone

from context_badge.dwell_report import (
    aggregate_by_app,
    clip_session,
    day_range,
    format_duration,
    format_percent,
    merge_adjacent_by_app,
    pan_view,
    slices_for_day,
    slices_in_range,
    tick_times,
    zoom_view,
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

    def test_format_percent_rounds_share_of_the_day(self) -> None:
        self.assertEqual(format_percent(20 * 60_000, 60 * 60_000), "33%")
        self.assertEqual(format_percent(0, 0), "0%")

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

    def test_zoom_in_keeps_the_anchor_visible(self) -> None:
        start, end = day_range(date(2026, 8, 16), tzinfo=TZ)
        anchor = datetime(2026, 8, 16, 7, 30, tzinfo=TZ)
        zoomed_start, zoomed_end = zoom_view(start, end, start, end, anchor, 0.125)
        self.assertEqual(zoomed_end - zoomed_start, timedelta(hours=3))
        self.assertLessEqual(zoomed_start, anchor)
        self.assertGreaterEqual(zoomed_end, anchor)

    def test_zoom_out_returns_to_the_full_day(self) -> None:
        start, end = day_range(date(2026, 8, 16), tzinfo=TZ)
        view_start = datetime(2026, 8, 16, 6, tzinfo=TZ)
        view_end = datetime(2026, 8, 16, 9, tzinfo=TZ)
        zoomed_start, zoomed_end = zoom_view(
            start, end, view_start, view_end, view_start, 8
        )
        self.assertEqual(zoomed_start, start)
        self.assertEqual(zoomed_end, end)

    def test_pan_does_not_leave_the_day(self) -> None:
        start, end = day_range(date(2026, 8, 16), tzinfo=TZ)
        view_start = datetime(2026, 8, 16, 6, tzinfo=TZ)
        view_end = datetime(2026, 8, 16, 9, tzinfo=TZ)
        panned_start, panned_end = pan_view(
            start, end, view_start, view_end, timedelta(hours=-10)
        )
        self.assertEqual(panned_start, start)
        self.assertEqual(panned_end - panned_start, timedelta(hours=3))

    def test_three_hour_window_uses_hourly_ticks(self) -> None:
        view_start = datetime(2026, 8, 16, 6, tzinfo=TZ)
        view_end = datetime(2026, 8, 16, 9, tzinfo=TZ)
        hours = [tick.hour for tick in tick_times(view_start, view_end)]
        self.assertEqual(hours, [6, 7, 8, 9])

    def test_slices_in_range_clip_to_the_visible_window(self) -> None:
        records = [
            session("Chrome", "2026-08-16T05:00:00+00:00", "2026-08-16T08:00:00+00:00")
        ]
        slices = slices_for_day(records, date(2026, 8, 16), tzinfo=TZ)
        visible = slices_in_range(
            slices,
            datetime(2026, 8, 16, 6, tzinfo=TZ),
            datetime(2026, 8, 16, 9, tzinfo=TZ),
        )
        self.assertEqual(len(visible), 1)
        self.assertEqual(visible[0].duration_ms, 2 * 60 * 60 * 1000)


if __name__ == "__main__":
    unittest.main()
