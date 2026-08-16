"""Standalone Time analysis window for a selected day's dwell records."""

from __future__ import annotations

import tkinter as tk
from collections.abc import Callable
from datetime import date, timedelta

from .dwell_report import (
    AppTotal,
    DaySlice,
    aggregate_by_app,
    app_colour,
    day_range,
    format_clock,
    format_duration,
    merge_adjacent_by_app,
    slices_for_day,
)

BG = "#1b1e24"
PANEL = "#20232a"
TEXT = "#f3f5f7"
MUTED = "#aab3c2"
LINE = "#3b404b"
ACCENT = "#8fc0ff"
WINDOW_WIDTH = 560
WINDOW_HEIGHT = 640
APP_ROW = 30
APP_VIEW = 180
TIMELINE_ROW = 32
TIMELINE_VIEW = 268
RIBBON_HEIGHT = 58


class AnalysisWindow:
    """Dark, scrollable day report: app totals plus an action timeline."""

    def __init__(
        self,
        parent: tk.Tk,
        records: Callable[[], list[dict]],
    ) -> None:
        self._records = records
        self.day = date.today()
        self.slices: list[DaySlice] = []
        self.totals: list[AppTotal] = []

        self.window = tk.Toplevel(parent)
        self.window.withdraw()
        self.window.title("Context Badge — Time")
        self.window.configure(bg=BG)
        self.window.geometry(f"{WINDOW_WIDTH}x{WINDOW_HEIGHT}")
        self.window.minsize(480, 520)
        self.window.protocol("WM_DELETE_WINDOW", self.hide)
        self.window.bind("<Escape>", lambda _event: self.hide())

        header = tk.Frame(self.window, bg=BG)
        header.pack(fill="x", padx=16, pady=(14, 6))
        self._nav_button(header, "‹", self._prev_day).pack(side="left")
        self.date_label = tk.Label(
            header,
            text="",
            bg=BG,
            fg=TEXT,
            font=("Segoe UI Semibold", 13),
        )
        self.date_label.pack(side="left", expand=True)
        self._nav_button(header, "›", self._next_day).pack(side="left")
        self._nav_button(header, "Today", self._goto_today, width=7).pack(
            side="right", padx=(10, 0)
        )

        self.summary = tk.Label(
            self.window,
            text="",
            bg=BG,
            fg=MUTED,
            font=("Segoe UI", 10),
            anchor="w",
        )
        self.summary.pack(fill="x", padx=18, pady=(0, 8))

        tk.Label(
            self.window,
            text="Apps",
            bg=BG,
            fg=MUTED,
            font=("Segoe UI Semibold", 9),
            anchor="w",
        ).pack(fill="x", padx=18)
        self.apps_holder, self.apps = self._scrolled_canvas(APP_VIEW)
        self.apps_holder.pack(fill="x", padx=12, pady=(2, 10))

        tk.Label(
            self.window,
            text="Day",
            bg=BG,
            fg=MUTED,
            font=("Segoe UI Semibold", 9),
            anchor="w",
        ).pack(fill="x", padx=18)
        self.ribbon = tk.Canvas(
            self.window,
            height=RIBBON_HEIGHT,
            bg=PANEL,
            highlightthickness=1,
            highlightbackground=LINE,
        )
        self.ribbon.pack(fill="x", padx=12, pady=(2, 10))
        self.ribbon.bind("<Configure>", lambda _event: self._draw_ribbon())

        tk.Label(
            self.window,
            text="Timeline",
            bg=BG,
            fg=MUTED,
            font=("Segoe UI Semibold", 9),
            anchor="w",
        ).pack(fill="x", padx=18)
        self.timeline_holder, self.timeline = self._scrolled_canvas(TIMELINE_VIEW)
        self.timeline_holder.pack(fill="both", expand=True, padx=12, pady=(2, 14))
        self.apps.bind(
            "<MouseWheel>",
            lambda event: self.apps.yview_scroll(int(-event.delta / 120), "units"),
        )
        self.timeline.bind(
            "<MouseWheel>",
            lambda event: self.timeline.yview_scroll(
                int(-event.delta / 120), "units"
            ),
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

    def show(self, x: int, y: int) -> None:
        self.day = date.today()
        self.window.geometry(f"{WINDOW_WIDTH}x{WINDOW_HEIGHT}+{x}+{y}")
        self.window.deiconify()
        self.window.lift()
        self.window.focus_force()
        self.reload()
        self.window.after_idle(self.reload)

    def hide(self) -> None:
        self.window.withdraw()

    def _prev_day(self) -> None:
        self.day -= timedelta(days=1)
        self.reload()

    def _next_day(self) -> None:
        if self.day < date.today():
            self.day += timedelta(days=1)
            self.reload()

    def _goto_today(self) -> None:
        self.day = date.today()
        self.reload()

    def reload(self) -> None:
        self.slices = slices_for_day(self._records(), self.day)
        self.totals = aggregate_by_app(self.slices)
        suffix = "  ·  Today" if self.day == date.today() else ""
        self.date_label.configure(text=self.day.strftime("%a %d %b %Y") + suffix)
        total_ms = sum(item.duration_ms for item in self.slices)
        self.summary.configure(
            text=(
                f"{format_duration(total_ms)}  ·  {len(self.totals)} apps  ·  "
                f"{len(self.slices)} switches"
                if self.slices
                else "No recorded time this day"
            )
        )
        self._draw_apps()
        self._draw_ribbon()
        self._draw_timeline()

    def _draw_apps(self) -> None:
        canvas = self.apps
        canvas.delete("all")
        width = max(120, canvas.winfo_width())
        if width <= 1:
            width = WINDOW_WIDTH - 40
        if not self.totals:
            canvas.create_text(
                14, 16, anchor="w", fill=MUTED, font=("Segoe UI", 10),
                text="Nothing to summarise yet.",
            )
            canvas.configure(scrollregion=(0, 0, width, APP_VIEW))
            return
        peak = max(item.duration_ms for item in self.totals) or 1
        bar_left = 168
        bar_right = width - 72
        bar_span = max(40, bar_right - bar_left)
        for index, item in enumerate(self.totals):
            top = index * APP_ROW + 6
            canvas.create_text(
                12,
                top + 8,
                anchor="w",
                fill=TEXT,
                font=("Segoe UI", 10),
                text=_ellipsis(item.app, 22),
            )
            filled = int(bar_span * item.duration_ms / peak)
            canvas.create_rectangle(
                bar_left,
                top + 4,
                bar_left + filled,
                top + 16,
                fill=app_colour(item.app),
                outline="",
            )
            canvas.create_text(
                width - 12,
                top + 8,
                anchor="e",
                fill=MUTED,
                font=("Segoe UI", 9),
                text=format_duration(item.duration_ms),
            )
        canvas.configure(scrollregion=(0, 0, width, max(APP_VIEW, len(self.totals) * APP_ROW + 8)))

    def _draw_ribbon(self) -> None:
        canvas = self.ribbon
        canvas.delete("all")
        width = max(120, canvas.winfo_width())
        height = RIBBON_HEIGHT
        pad_x = 12
        pad_top = 8
        pad_bottom = 18
        left = pad_x
        right = width - pad_x
        top = pad_top
        bottom = height - pad_bottom
        canvas.create_rectangle(left, top, right, bottom, fill="#16181d", outline=LINE)
        day_start, day_end = day_range(self.day)
        span = (day_end - day_start).total_seconds() or 1
        usable = max(1, right - left)
        for item in merge_adjacent_by_app(self.slices):
            x1 = left + usable * ((item.started_at - day_start).total_seconds() / span)
            x2 = left + usable * ((item.ended_at - day_start).total_seconds() / span)
            if x2 - x1 < 1:
                x2 = x1 + 1
            canvas.create_rectangle(
                x1, top + 1, x2, bottom - 1,
                fill=app_colour(item.app), outline="",
            )
        for hour in (0, 6, 12, 18, 24):
            x = left + usable * (hour / 24)
            canvas.create_text(
                x,
                height - 8,
                text=f"{hour:02d}",
                fill=MUTED,
                font=("Segoe UI", 8),
            )

    def _draw_timeline(self) -> None:
        canvas = self.timeline
        canvas.delete("all")
        width = max(120, canvas.winfo_width())
        if width <= 1:
            width = WINDOW_WIDTH - 40
        if not self.slices:
            canvas.create_text(
                14, 16, anchor="w", fill=MUTED, font=("Segoe UI", 10),
                text="No switches recorded for this date.",
            )
            canvas.configure(scrollregion=(0, 0, width, TIMELINE_VIEW))
            canvas.yview_moveto(0)
            return
        for index, item in enumerate(self.slices):
            top = index * TIMELINE_ROW
            if index:
                canvas.create_line(12, top, width - 12, top, fill=LINE)
            canvas.create_rectangle(
                12,
                top + 10,
                18,
                top + 22,
                fill=app_colour(item.app),
                outline="",
            )
            clock = f"{format_clock(item.started_at)}–{format_clock(item.ended_at)}"
            canvas.create_text(
                26,
                top + 8,
                anchor="nw",
                fill=MUTED,
                font=("Segoe UI", 9),
                text=clock,
            )
            canvas.create_text(
                108,
                top + 8,
                anchor="nw",
                fill=TEXT,
                font=("Segoe UI Semibold", 10),
                text=_ellipsis(item.app, 18),
            )
            canvas.create_text(
                width - 12,
                top + 8,
                anchor="ne",
                fill=MUTED,
                font=("Segoe UI", 9),
                text=format_duration(item.duration_ms),
            )
            canvas.create_text(
                108,
                top + 22,
                anchor="nw",
                fill=MUTED,
                font=("Segoe UI", 9),
                text=_ellipsis(item.surface, 52),
            )
        canvas.configure(
            scrollregion=(0, 0, width, max(TIMELINE_VIEW, len(self.slices) * TIMELINE_ROW + 8))
        )
        canvas.yview_moveto(0)


def _ellipsis(text: str, limit: int) -> str:
    cleaned = " ".join(text.split())
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[: max(1, limit - 1)].rstrip() + "…"
