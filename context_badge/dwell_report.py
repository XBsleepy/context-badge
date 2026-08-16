"""Pure dwell reporting helpers: day slices, app totals, and formatting."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any

APP_COLOURS = (
    "#5b8def",
    "#34d399",
    "#fbbf24",
    "#f472b6",
    "#a78bfa",
    "#22d3ee",
    "#fb7185",
    "#84cc16",
)


@dataclass(frozen=True)
class DaySlice:
    app: str
    surface: str
    title: str
    started_at: datetime
    ended_at: datetime
    duration_ms: int


@dataclass(frozen=True)
class AppTotal:
    app: str
    duration_ms: int
    count: int


def local_tzinfo():
    return datetime.now().astimezone().tzinfo


def parse_datetime(value: object, *, tzinfo=None) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=tzinfo or local_tzinfo())
    return parsed


def day_range(day: date, *, tzinfo=None) -> tuple[datetime, datetime]:
    zone = tzinfo or local_tzinfo()
    start = datetime(day.year, day.month, day.day, tzinfo=zone)
    return start, start + timedelta(days=1)


def session_end(session: dict[str, Any], start: datetime) -> datetime:
    ended = parse_datetime(session.get("ended_at"), tzinfo=start.tzinfo)
    if ended is not None:
        return ended
    updated = parse_datetime(session.get("updated_at"), tzinfo=start.tzinfo)
    if updated is not None:
        return updated
    duration_ms = _int_field(session.get("duration_ms"), 0)
    return start + timedelta(milliseconds=max(0, duration_ms))


def clip_session(
    session: dict[str, Any], day_start: datetime, day_end: datetime
) -> DaySlice | None:
    start = parse_datetime(session.get("started_at"), tzinfo=day_start.tzinfo)
    if start is None:
        return None
    end = session_end(session, start)
    if end <= day_start or start >= day_end:
        return None
    clipped_start = max(start, day_start)
    clipped_end = min(end, day_end)
    duration_ms = int((clipped_end - clipped_start).total_seconds() * 1000)
    if duration_ms <= 0:
        return None
    app = str(session.get("app") or "Unknown").strip() or "Unknown"
    surface = str(session.get("surface") or session.get("title") or app)
    title = str(session.get("title") or surface)
    return DaySlice(
        app=app,
        surface=surface,
        title=title,
        started_at=clipped_start,
        ended_at=clipped_end,
        duration_ms=duration_ms,
    )


def slices_for_day(
    records: list[dict[str, Any]], day: date, *, tzinfo=None
) -> list[DaySlice]:
    day_start, day_end = day_range(day, tzinfo=tzinfo)
    slices = []
    for session in records:
        item = clip_session(session, day_start, day_end)
        if item is not None:
            slices.append(item)
    slices.sort(key=lambda item: item.started_at)
    return slices


def aggregate_by_app(slices: list[DaySlice]) -> list[AppTotal]:
    totals: dict[str, AppTotal] = {}
    for item in slices:
        current = totals.get(item.app)
        if current is None:
            totals[item.app] = AppTotal(item.app, item.duration_ms, 1)
        else:
            totals[item.app] = AppTotal(
                item.app,
                current.duration_ms + item.duration_ms,
                current.count + 1,
            )
    return sorted(
        totals.values(),
        key=lambda item: (-item.duration_ms, item.app.lower()),
    )


def format_duration(ms: int) -> str:
    seconds = max(0, int(ms) // 1000)
    hours, remainder = divmod(seconds, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours and minutes:
        return f"{hours}h {minutes}m"
    if hours:
        return f"{hours}h"
    if minutes:
        return f"{minutes}m"
    return f"{secs}s"


def format_clock(moment: datetime) -> str:
    return moment.strftime("%H:%M")


def format_percent(part_ms: int, total_ms: int) -> str:
    if total_ms <= 0:
        return "0%"
    return f"{round(100 * part_ms / total_ms)}%"


def app_colour(name: str) -> str:
    digest = 5381
    for character in name:
        digest = ((digest << 5) + digest + ord(character)) & 0xFFFFFFFF
    return APP_COLOURS[digest % len(APP_COLOURS)]


def merge_adjacent_by_app(slices: list[DaySlice]) -> list[DaySlice]:
    """Collapse consecutive same-app slices for compact overview bars."""
    if not slices:
        return []
    merged = [slices[0]]
    slack = timedelta(seconds=1)
    for item in slices[1:]:
        last = merged[-1]
        if item.app == last.app and item.started_at <= last.ended_at + slack:
            merged[-1] = DaySlice(
                app=last.app,
                surface=last.surface,
                title=last.title,
                started_at=last.started_at,
                ended_at=max(last.ended_at, item.ended_at),
                duration_ms=last.duration_ms + item.duration_ms,
            )
        else:
            merged.append(item)
    return merged


MIN_VIEW_SPAN = timedelta(minutes=30)


def clamp_view(
    full_start: datetime,
    full_end: datetime,
    start: datetime,
    end: datetime,
    *,
    min_span: timedelta = MIN_VIEW_SPAN,
) -> tuple[datetime, datetime]:
    """Keep a visible window inside the day and above the minimum span."""
    full_span = full_end - full_start
    span = max(min_span, min(full_span, end - start))
    if start < full_start:
        start = full_start
    end = start + span
    if end > full_end:
        end = full_end
        start = end - span
        if start < full_start:
            start = full_start
    return start, end


def zoom_view(
    full_start: datetime,
    full_end: datetime,
    view_start: datetime,
    view_end: datetime,
    anchor: datetime,
    factor: float,
    *,
    min_span: timedelta = MIN_VIEW_SPAN,
) -> tuple[datetime, datetime]:
    """Zoom the visible window around ``anchor``. ``factor`` < 1 zooms in."""
    span = view_end - view_start
    if span <= timedelta(0):
        return clamp_view(full_start, full_end, full_start, full_end, min_span=min_span)
    relative = 0.5
    if span.total_seconds():
        relative = (anchor - view_start) / span
        relative = min(1.0, max(0.0, relative))
    new_span = timedelta(seconds=span.total_seconds() * factor)
    new_start = anchor - new_span * relative
    new_end = new_start + new_span
    return clamp_view(full_start, full_end, new_start, new_end, min_span=min_span)


def pan_view(
    full_start: datetime,
    full_end: datetime,
    view_start: datetime,
    view_end: datetime,
    delta: timedelta,
) -> tuple[datetime, datetime]:
    """Slide the visible window without changing its length."""
    return clamp_view(
        full_start,
        full_end,
        view_start + delta,
        view_end + delta,
        min_span=view_end - view_start,
    )


def clip_slice(item: DaySlice, start: datetime, end: datetime) -> DaySlice | None:
    if item.ended_at <= start or item.started_at >= end:
        return None
    clipped_start = max(item.started_at, start)
    clipped_end = min(item.ended_at, end)
    duration_ms = int((clipped_end - clipped_start).total_seconds() * 1000)
    if duration_ms <= 0:
        return None
    return DaySlice(
        app=item.app,
        surface=item.surface,
        title=item.title,
        started_at=clipped_start,
        ended_at=clipped_end,
        duration_ms=duration_ms,
    )


def slices_in_range(
    slices: list[DaySlice], start: datetime, end: datetime
) -> list[DaySlice]:
    visible = []
    for item in slices:
        clipped = clip_slice(item, start, end)
        if clipped is not None:
            visible.append(clipped)
    return visible


def tick_times(view_start: datetime, view_end: datetime) -> list[datetime]:
    """Return axis labels that get denser as the visible window shrinks."""
    span = view_end - view_start
    if span <= timedelta(0):
        return [view_start]
    seconds = span.total_seconds()
    if seconds >= 12 * 3600:
        step = timedelta(hours=6)
    elif seconds >= 3 * 3600:
        step = timedelta(hours=1)
    elif seconds >= 3600:
        step = timedelta(minutes=15)
    else:
        step = timedelta(minutes=5)
    origin = view_start.replace(hour=0, minute=0, second=0, microsecond=0)
    step_s = step.total_seconds()
    start_s = (view_start - origin).total_seconds()
    first_s = (start_s // step_s) * step_s
    if first_s < start_s - 1e-6:
        first_s += step_s
    ticks: list[datetime] = []
    end_s = (view_end - origin).total_seconds()
    tick_s = first_s
    while tick_s <= end_s + 1e-6:
        ticks.append(origin + timedelta(seconds=tick_s))
        tick_s += step_s
    if not ticks or abs((ticks[0] - view_start).total_seconds()) > 1:
        ticks.insert(0, view_start)
    if abs((ticks[-1] - view_end).total_seconds()) > 1:
        ticks.append(view_end)
    return ticks


def format_tick(moment: datetime, span: timedelta) -> str:
    if span < timedelta(hours=4) or moment.minute or moment.second:
        return moment.strftime("%H:%M")
    return moment.strftime("%H")


def _int_field(value: object, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default
