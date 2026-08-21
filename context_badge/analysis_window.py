"""Standalone Time analysis window for a selected day's dwell records."""

from __future__ import annotations

import tkinter as tk
from collections.abc import Callable
from datetime import date, datetime, timedelta

from .dwell_report import (
    AppTotal,
    DaySlice,
    aggregate_by_app,
    app_colour,
    clamp_view,
    day_range,
    format_clock,
    format_duration,
    format_percent,
    format_tick,
    merge_adjacent_by_app,
    pan_view,
    slices_for_day,
    slices_in_range,
    tick_times,
    zoom_view,
)

BG = "#15181e"
PANEL = "#1e232c"
TEXT = "#f3f5f7"
MUTED = "#9aa3b2"
LINE = "#323844"
TRACK = "#12151a"
ACCENT = "#8fc0ff"
WINDOW_WIDTH = 580
WINDOW_HEIGHT = 680
APP_ROW = 46
APP_VIEW = 196
TIMELINE_ROW = 54
TIMELINE_VIEW = 280
RIBBON_HEIGHT = 72


class AnalysisWindow:
    """Dark, scrollable day report: app totals plus an action timeline."""

    def __init__(
        self,
        parent: tk.Tk,
        records: Callable[[date], list[dict]],
    ) -> None:
        self._records = records
        self.day = date.today()
        self.day_slices: list[DaySlice] = []
        self.slices: list[DaySlice] = []
        self.totals: list[AppTotal] = []
        self.view_start: datetime | None = None
        self.view_end: datetime | None = None
        self._rendered_day: date | None = None
        self._drag_origin: tuple[int, datetime, datetime] | None = None

        self.window = tk.Toplevel(parent)
        self.window.withdraw()
        self.window.title("Context Badge — Time")
        self.window.configure(bg=BG)
        self.window.geometry(f"{WINDOW_WIDTH}x{WINDOW_HEIGHT}")
        self.window.minsize(500, 560)
        self.window.protocol("WM_DELETE_WINDOW", self.hide)
        self.window.bind("<Escape>", lambda _event: self.hide())

        header = tk.Frame(self.window, bg=BG)
        header.pack(fill="x", padx=18, pady=(16, 4))
        self._nav_button(header, "‹", self._prev_day).pack(side="left")
        self._nav_button(header, "›", self._next_day).pack(side="left", padx=(6, 0))
        self.date_label = tk.Label(
            header,
            text="",
            bg=BG,
            fg=TEXT,
            font=("Segoe UI Semibold", 14),
        )
        self.date_label.pack(side="left", padx=(14, 0))
        self._nav_button(header, "Today", self._goto_today, width=7).pack(
            side="right"
        )

        self.total_label = tk.Label(
            self.window,
            text="0s",
            bg=BG,
            fg=TEXT,
            font=("Segoe UI Semibold", 28),
            anchor="w",
        )
        self.total_label.pack(fill="x", padx=20, pady=(8, 0))
        self.summary = tk.Label(
            self.window,
            text="",
            bg=BG,
            fg=MUTED,
            font=("Segoe UI", 10),
            anchor="w",
        )
        self.summary.pack(fill="x", padx=20, pady=(0, 12))

        self._section("Apps").pack(fill="x", padx=20)
        self.apps_holder, self.apps = self._scrolled_canvas(APP_VIEW)
        self.apps_holder.pack(fill="x", padx=14, pady=(4, 12))

        self._section("Day").pack(fill="x", padx=20)
        self.ribbon = tk.Canvas(
            self.window,
            height=RIBBON_HEIGHT,
            bg=PANEL,
            highlightthickness=1,
            highlightbackground=LINE,
        )
        self.ribbon.pack(fill="x", padx=14, pady=(4, 12))
        self.ribbon.bind("<Configure>", lambda _event: self._draw_ribbon())
        self.ribbon.bind("<MouseWheel>", self._on_ribbon_wheel)
        self.ribbon.bind("<ButtonPress-1>", self._on_ribbon_press)
        self.ribbon.bind("<B1-Motion>", self._on_ribbon_drag)
        self.ribbon.bind("<Double-Button-1>", self._on_ribbon_reset)
        self.ribbon.bind("<Enter>", lambda _event: self.ribbon.focus_set())
        self.ribbon.configure(cursor="sb_h_double_arrow")

        self._section("Timeline").pack(fill="x", padx=20)
        self.timeline_holder, self.timeline = self._scrolled_canvas(TIMELINE_VIEW)
        self.timeline_holder.pack(fill="both", expand=True, padx=14, pady=(4, 16))
        self._bind_wheel(self.apps)
        self._bind_wheel(self.timeline)

    def _section(self, title: str) -> tk.Label:
        return tk.Label(
            self.window,
            text=title.upper(),
            bg=BG,
            fg=MUTED,
            font=("Segoe UI Semibold", 8),
            anchor="w",
        )

    def _nav_button(
        self,
        parent: tk.Frame,
        text: str,
        command: Callable[[], None],
        width: int = 3,
    ) -> tk.Button:
        return tk.Button(
            parent,
            text=text,
            command=command,
            width=width,
            bg=PANEL,
            fg=TEXT,
            activebackground=LINE,
            activeforeground=TEXT,
            relief="flat",
            bd=0,
            highlightthickness=0,
            font=("Segoe UI Semibold", 11),
            cursor="hand2",
            padx=8,
            pady=4,
        )

    def _scrolled_canvas(self, height: int) -> tuple[tk.Frame, tk.Canvas]:
        holder = tk.Frame(self.window, bg=BG)
        canvas = tk.Canvas(
            holder,
            height=height,
            bg=PANEL,
            highlightthickness=1,
            highlightbackground=LINE,
        )
        scroll = tk.Scrollbar(
            holder,
            orient="vertical",
            command=canvas.yview,
            bg=PANEL,
            troughcolor=BG,
            activebackground=ACCENT,
        )
        canvas.configure(yscrollcommand=scroll.set)
        canvas.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")
        return holder, canvas

    def _bind_wheel(self, canvas: tk.Canvas) -> None:
        canvas.bind(
            "<MouseWheel>",
            lambda event: canvas.yview_scroll(int(-event.delta / 120), "units"),
        )
        canvas.bind("<Enter>", lambda _event: canvas.focus_set())

    def show(self, x: int, y: int) -> None:
        self.day = date.today()
        self._rendered_day = None
        self.view_start = None
        self.view_end = None
        self.window.attributes("-topmost", True)
        self.window.geometry(f"{WINDOW_WIDTH}x{WINDOW_HEIGHT}+{x}+{y}")
        self.window.deiconify()
        self.window.lift()
        self.window.focus_force()
        self.reload()

    def hide(self) -> None:
        self.window.attributes("-topmost", False)
        self.window.withdraw()

    def prompt_text(self) -> str:
        total_ms = sum(item.duration_ms for item in self.day_slices)
        day = self.day.strftime("%d %b")
        if not self.day_slices:
            return f"{day} · no time yet"
        return f"{day} · {format_duration(total_ms)}"

    def _prev_day(self) -> None:
        self.day -= timedelta(days=1)
        self._reset_view()
        self.reload()

    def _next_day(self) -> None:
        if self.day < date.today():
            self.day += timedelta(days=1)
            self._reset_view()
            self.reload()

    def _goto_today(self) -> None:
        self.day = date.today()
        self._reset_view()
        self.reload()

    def _reset_view(self) -> None:
        self.view_start = None
        self.view_end = None

    def _full_bounds(self) -> tuple[datetime, datetime]:
        return day_range(self.day)

    def _view_bounds(self) -> tuple[datetime, datetime]:
        full_start, full_end = self._full_bounds()
        if self.view_start is None or self.view_end is None:
            return full_start, full_end
        return clamp_view(full_start, full_end, self.view_start, self.view_end)

    def _is_zoomed(self) -> bool:
        full_start, full_end = self._full_bounds()
        view_start, view_end = self._view_bounds()
        return (view_end - view_start) < (full_end - full_start - timedelta(seconds=30))

    def _ribbon_track(self) -> tuple[float, float, float, float, float]:
        width = max(160, self.ribbon.winfo_width())
        left = 14.0
        right = width - 14.0
        top = 10.0
        bottom = RIBBON_HEIGHT - 22.0
        return left, right, top, bottom, max(1.0, right - left)

    def _time_at(self, x: float) -> datetime:
        left, _right, _top, _bottom, usable = self._ribbon_track()
        view_start, view_end = self._view_bounds()
        relative = min(1.0, max(0.0, (x - left) / usable))
        return view_start + (view_end - view_start) * relative

    def _on_ribbon_wheel(self, event: tk.Event) -> str:
        full_start, full_end = self._full_bounds()
        view_start, view_end = self._view_bounds()
        factor = 0.8 if event.delta > 0 else 1.25
        self.view_start, self.view_end = zoom_view(
            full_start,
            full_end,
            view_start,
            view_end,
            self._time_at(event.x),
            factor,
        )
        self._apply_view()
        return "break"

    def _on_ribbon_press(self, event: tk.Event) -> None:
        view_start, view_end = self._view_bounds()
        self._drag_origin = (event.x, view_start, view_end)

    def _on_ribbon_drag(self, event: tk.Event) -> None:
        if self._drag_origin is None:
            return
        origin_x, origin_start, origin_end = self._drag_origin
        _left, _right, _top, _bottom, usable = self._ribbon_track()
        span = origin_end - origin_start
        shift = span * ((event.x - origin_x) / usable)
        full_start, full_end = self._full_bounds()
        self.view_start, self.view_end = pan_view(
            full_start, full_end, origin_start, origin_end, -shift
        )
        self._apply_view()

    def _on_ribbon_reset(self, _event: tk.Event) -> None:
        self._reset_view()
        self._drag_origin = None
        self._apply_view(reset_scroll=True)

    def _apply_view(self, *, reset_scroll: bool = False) -> None:
        view_start, view_end = self._view_bounds()
        self.view_start, self.view_end = view_start, view_end
        self.slices = slices_in_range(self.day_slices, view_start, view_end)
        self.totals = aggregate_by_app(self.slices)
        total_ms = sum(item.duration_ms for item in self.slices)
        self.total_label.configure(
            text=format_duration(total_ms) if self.slices else "0s"
        )
        zoomed = self._is_zoomed()
        range_text = f"{format_clock(view_start)}–{format_clock(view_end)}"
        if not self.day_slices:
            self.summary.configure(text="No recorded time this day")
        elif zoomed:
            self.summary.configure(
                text=(
                    f"{range_text}  ·  {len(self.totals)} apps  ·  "
                    f"{len(self.slices)} switches  ·  drag to pan, double-click to reset"
                )
            )
        else:
            self.summary.configure(
                text=(
                    f"{len(self.totals)} apps  ·  {len(self.slices)} switches  ·  "
                    "scroll the colour bar to zoom"
                )
            )
        self._draw_apps()
        self._draw_ribbon()
        self._draw_timeline(reset_scroll=reset_scroll)

    def reload(self) -> None:
        reset_scroll = self._rendered_day != self.day
        if reset_scroll:
            self._reset_view()
        self.day_slices = slices_for_day(self._records(self.day), self.day)
        self._rendered_day = self.day
        suffix = "  ·  Today" if self.day == date.today() else ""
        self.date_label.configure(text=self.day.strftime("%a %d %b %Y") + suffix)
        self._apply_view(reset_scroll=reset_scroll)

    def _draw_apps(self) -> None:
        canvas = self.apps
        canvas.delete("all")
        width = max(160, canvas.winfo_width())
        if width <= 1:
            width = WINDOW_WIDTH - 44
        if not self.totals:
            canvas.create_text(
                16,
                20,
                anchor="w",
                fill=MUTED,
                font=("Segoe UI", 10),
                text="Nothing to summarise yet.",
            )
            canvas.configure(scrollregion=(0, 0, width, APP_VIEW))
            return
        peak = max(item.duration_ms for item in self.totals) or 1
        total_ms = sum(item.duration_ms for item in self.totals) or 1
        bar_left = 16
        bar_right = width - 16
        bar_span = max(48, bar_right - bar_left)
        for index, item in enumerate(self.totals):
            top = index * APP_ROW + 8
            colour = app_colour(item.app)
            canvas.create_oval(16, top + 4, 26, top + 14, fill=colour, outline="")
            canvas.create_text(
                34,
                top + 8,
                anchor="w",
                fill=TEXT,
                font=("Segoe UI Semibold", 10),
                text=_ellipsis(item.app, 28),
            )
            canvas.create_text(
                width - 16,
                top + 8,
                anchor="e",
                fill=MUTED,
                font=("Segoe UI", 9),
                text=f"{format_percent(item.duration_ms, total_ms)}  {format_duration(item.duration_ms)}",
            )
            filled = int(bar_span * item.duration_ms / peak)
            canvas.create_rectangle(
                bar_left,
                top + 22,
                bar_right,
                top + 30,
                fill=TRACK,
                outline="",
            )
            canvas.create_rectangle(
                bar_left,
                top + 22,
                bar_left + max(3, filled),
                top + 30,
                fill=colour,
                outline="",
            )
        canvas.configure(
            scrollregion=(0, 0, width, max(APP_VIEW, len(self.totals) * APP_ROW + 12))
        )

    def _draw_ribbon(self) -> None:
        canvas = self.ribbon
        canvas.delete("all")
        width = max(160, canvas.winfo_width())
        height = RIBBON_HEIGHT
        pad_x = 14
        pad_top = 10
        pad_bottom = 22
        left = pad_x
        right = width - pad_x
        top = pad_top
        bottom = height - pad_bottom
        canvas.create_rectangle(left, top, right, bottom, fill=TRACK, outline=LINE)
        view_start, view_end = self._view_bounds()
        span = view_end - view_start
        span_s = span.total_seconds() or 1
        usable = max(1.0, right - left)
        for item in merge_adjacent_by_app(self.slices):
            x1 = left + usable * ((item.started_at - view_start).total_seconds() / span_s)
            x2 = left + usable * ((item.ended_at - view_start).total_seconds() / span_s)
            if x2 - x1 < 2:
                x2 = x1 + 2
            canvas.create_rectangle(
                x1,
                top + 1,
                x2,
                bottom - 1,
                fill=app_colour(item.app),
                outline="",
            )
        if self.day == date.today():
            now = datetime.now().astimezone()
            if view_start <= now <= view_end:
                x_now = left + usable * ((now - view_start).total_seconds() / span_s)
                canvas.create_line(x_now, top, x_now, bottom, fill="#ffffff", width=1)
        for moment in tick_times(view_start, view_end):
            x = left + usable * ((moment - view_start).total_seconds() / span_s)
            canvas.create_text(
                x,
                height - 10,
                text=format_tick(moment, span),
                fill=MUTED,
                font=("Segoe UI", 8),
            )

    def _draw_timeline(self, *, reset_scroll: bool = False) -> None:
        canvas = self.timeline
        canvas.delete("all")
        width = max(160, canvas.winfo_width())
        if width <= 1:
            width = WINDOW_WIDTH - 44
        if not self.slices:
            canvas.create_text(
                16,
                20,
                anchor="w",
                fill=MUTED,
                font=("Segoe UI", 10),
                text="No switches recorded for this date.",
            )
            canvas.configure(scrollregion=(0, 0, width, TIMELINE_VIEW))
            if reset_scroll:
                canvas.yview_moveto(0)
            return
        for index, item in enumerate(self.slices):
            top = index * TIMELINE_ROW
            if index:
                canvas.create_line(14, top, width - 14, top, fill=LINE)
            colour = app_colour(item.app)
            canvas.create_oval(16, top + 12, 26, top + 22, fill=colour, outline="")
            clock = f"{format_clock(item.started_at)}  –  {format_clock(item.ended_at)}"
            canvas.create_text(
                36,
                top + 8,
                anchor="nw",
                fill=MUTED,
                font=("Segoe UI", 9),
                text=clock,
            )
            canvas.create_text(
                width - 16,
                top + 8,
                anchor="ne",
                fill=ACCENT,
                font=("Segoe UI Semibold", 10),
                text=format_duration(item.duration_ms),
            )
            canvas.create_text(
                36,
                top + 24,
                anchor="nw",
                fill=TEXT,
                font=("Segoe UI Semibold", 10),
                text=_ellipsis(item.app, 28),
            )
            canvas.create_text(
                36,
                top + 40,
                anchor="nw",
                fill=MUTED,
                font=("Segoe UI", 9),
                text=_ellipsis(item.surface, 56),
            )
        canvas.configure(
            scrollregion=(
                0,
                0,
                width,
                max(TIMELINE_VIEW, len(self.slices) * TIMELINE_ROW + 10),
            )
        )
        if reset_scroll:
            canvas.yview_moveto(0)


def _ellipsis(text: str, limit: int) -> str:
    cleaned = " ".join(text.split())
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[: max(1, limit - 1)].rstrip() + "…"
