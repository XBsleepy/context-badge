"""Pet-central rest clock: countdown shown by clicking the pet."""

from __future__ import annotations

import tkinter as tk
from collections.abc import Callable

from .bubble import draw_rounded_panel
from .rest_timer import format_countdown, format_rest_interval
from .theme import TRANSPARENT_KEY, is_transparent, paint_color
from .win32 import (
    GWL_EXSTYLE,
    HWND_TOPMOST,
    SWP_FRAMECHANGED,
    SWP_NOACTIVATE,
    SWP_NOMOVE,
    SWP_NOSIZE,
    SWP_SHOWWINDOW,
    SW_HIDE,
    SW_SHOWNOACTIVATE,
    WS_EX_LAYERED,
    WS_EX_NOACTIVATE,
    WS_EX_TOOLWINDOW,
    WS_EX_TRANSPARENT,
    user32,
)

CLOCK_WIDTH = 168
CLOCK_HEIGHT = 118
PAD = 12
INSET = 2


class PetClock:
    """Compact countdown flyout anchored near the pet."""

    def __init__(
        self,
        parent: tk.Misc,
        *,
        on_action: Callable[[str], None] | None = None,
    ) -> None:
        self.on_action = on_action
        self.open = False
        self._anchor_x = 0
        self._anchor_y = 0
        self._fill = "#101218"
        self._text = "#f4f1ea"
        self._muted = "#aab3c2"
        self._border = "#8a8175"
        self._radius = 12
        self._enabled = False
        self._paused = False
        self._awaiting = False
        self._on_break = False
        self._remaining_ms = 0
        self._interval_seconds = 3600

        self.window = tk.Toplevel(parent)
        self.window.title("Rest clock")
        self.window.overrideredirect(True)
        self.window.attributes("-topmost", True)
        self.window.configure(bg=TRANSPARENT_KEY)
        self.window.attributes("-transparentcolor", TRANSPARENT_KEY)
        self.canvas = tk.Canvas(
            self.window,
            width=CLOCK_WIDTH,
            height=CLOCK_HEIGHT,
            bg=TRANSPARENT_KEY,
            highlightthickness=0,
            bd=0,
            cursor="hand2",
        )
        self.canvas.pack()
        self.canvas.bind("<Button-1>", self._on_click)
        self.window.update_idletasks()
        inner = self.window.winfo_id()
        self.hwnd = user32.GetParent(inner) or inner
        self._apply_window_style()
        self.window.withdraw()

    def _apply_window_style(self) -> None:
        style = user32.GetWindowLongW(self.hwnd, GWL_EXSTYLE)
        style |= WS_EX_LAYERED | WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE
        style &= ~WS_EX_TRANSPARENT
        user32.SetWindowLongW(self.hwnd, GWL_EXSTYLE, style)
        user32.SetWindowPos(
            self.hwnd,
            HWND_TOPMOST,
            0,
            0,
            0,
            0,
            SWP_NOSIZE | SWP_NOMOVE | SWP_NOACTIVATE | SWP_FRAMECHANGED,
        )

    def apply_chrome(
        self,
        *,
        fill: str,
        text: str,
        muted: str,
        border: str,
        radius: int,
        background: str,
    ) -> None:
        self._fill = paint_color(fill, "#101218")
        if is_transparent(fill):
            self._fill = paint_color(background, "#16181d")
        self._text = text
        self._muted = muted
        self._border = border
        self._radius = max(0, int(radius))
        if self.open:
            self._render()

    def set_state(
        self,
        *,
        enabled: bool,
        paused: bool,
        remaining_ms: int,
        interval_seconds: int,
        awaiting: bool = False,
        on_break: bool = False,
    ) -> None:
        self._enabled = bool(enabled)
        self._paused = bool(paused)
        self._awaiting = bool(awaiting)
        self._on_break = bool(on_break)
        self._remaining_ms = max(0, int(remaining_ms))
        self._interval_seconds = int(interval_seconds)
        if self.open:
            self._render()

    def show_at(self, x: int, y: int) -> None:
        self._anchor_x = int(x)
        self._anchor_y = int(y)
        self.open = True
        self._render()
        self.window.deiconify()
        self._apply_window_style()
        user32.ShowWindow(self.hwnd, SW_SHOWNOACTIVATE)
        self.window.lift()
        self._place()

    def hide(self) -> None:
        self.open = False
        user32.ShowWindow(self.hwnd, SW_HIDE)
        self.window.withdraw()

    def toggle_at(self, x: int, y: int) -> None:
        if self.open:
            self.hide()
        else:
            self.show_at(x, y)

    def set_position(self, x: int, y: int) -> None:
        self._anchor_x = int(x)
        self._anchor_y = int(y)
        if self.open:
            self._place()

    def raise_popup(self) -> None:
        if not self.open:
            return
        user32.SetWindowPos(
            self.hwnd,
            HWND_TOPMOST,
            0,
            0,
            0,
            0,
            SWP_NOSIZE | SWP_NOMOVE | SWP_NOACTIVATE | SWP_SHOWWINDOW,
        )

    def _place(self) -> None:
        left = self._anchor_x - CLOCK_WIDTH // 2
        top = self._anchor_y - CLOCK_HEIGHT - 8
        self.window.geometry(f"{CLOCK_WIDTH}x{CLOCK_HEIGHT}+{left}+{top}")
        user32.SetWindowPos(
            self.hwnd,
            HWND_TOPMOST,
            left,
            top,
            CLOCK_WIDTH,
            CLOCK_HEIGHT,
            SWP_NOACTIVATE | SWP_SHOWWINDOW,
        )

    def _status_label(self) -> str:
        if not self._enabled:
            return "Timer off"
        if self._on_break:
            return "Resting — Ack when back"
        if self._awaiting:
            return "Time to rest"
        if self._paused:
            return "Paused"
        return f"Every {format_rest_interval(self._interval_seconds)}"

    def _render(self) -> None:
        self.canvas.delete("all")
        self.canvas.configure(width=CLOCK_WIDTH, height=CLOCK_HEIGHT)
        draw_rounded_panel(
            self.canvas,
            INSET,
            INSET,
            CLOCK_WIDTH - INSET,
            CLOCK_HEIGHT - INSET,
            fill=self._fill,
            outline=self._border,
            radius=self._radius,
            width=2,
            tags="chrome",
        )
        self.canvas.create_text(
            CLOCK_WIDTH // 2,
            18,
            text="Break",
            fill=self._muted,
            font=("Segoe UI Semibold", 9),
            tags="chrome",
        )
        countdown = (
            format_countdown(self._remaining_ms)
            if self._enabled
            else "--:--"
        )
        self.canvas.create_text(
            CLOCK_WIDTH // 2,
            48,
            text=countdown,
            fill=self._text,
            font=("Segoe UI Semibold", 22),
            tags="chrome",
        )
        self.canvas.create_text(
            CLOCK_WIDTH // 2,
            74,
            text=self._status_label(),
            fill=self._muted,
            font=("Segoe UI", 9),
            tags="chrome",
        )
        # Compact actions
        btn_y1 = CLOCK_HEIGHT - 30
        btn_y2 = CLOCK_HEIGHT - 10
        mid = CLOCK_WIDTH // 2
        if self._enabled:
            if self._on_break:
                self._pill(PAD, btn_y1, mid - 4, btn_y2, "ack", "Ack")
                self._pill(mid + 4, btn_y1, CLOCK_WIDTH - PAD, btn_y2, "off", "Off")
            elif self._awaiting:
                self._pill(PAD, btn_y1, mid - 4, btn_y2, "rest", "Rest")
                self._pill(mid + 4, btn_y1, CLOCK_WIDTH - PAD, btn_y2, "pause", "Pause")
            else:
                pause_label = "Resume" if self._paused else "Pause"
                self._pill(PAD, btn_y1, mid - 4, btn_y2, "pause", pause_label)
                self._pill(mid + 4, btn_y1, CLOCK_WIDTH - PAD, btn_y2, "off", "Off")
        else:
            self._pill(PAD, btn_y1, CLOCK_WIDTH - PAD, btn_y2, "on", "Start")

    def _pill(
        self,
        x1: int,
        y1: int,
        x2: int,
        y2: int,
        action: str,
        label: str,
    ) -> None:
        tag = f"clock:{action}"
        draw_rounded_panel(
            self.canvas,
            x1,
            y1,
            x2,
            y2,
            fill=self._text,
            outline=self._border,
            radius=min(10, (y2 - y1) // 2),
            width=1,
            tags=tag,
        )
        self.canvas.create_text(
            (x1 + x2) // 2,
            (y1 + y2) // 2,
            text=label,
            fill=self._fill,
            font=("Segoe UI Semibold", 8),
            tags=tag,
        )

    def _on_click(self, event: tk.Event) -> None:
        items = self.canvas.find_overlapping(event.x, event.y, event.x, event.y)
        tags: list[str] = []
        for item in reversed(items):
            tags.extend(str(tag) for tag in self.canvas.gettags(item))
        for tag in tags:
            if tag.startswith("clock:"):
                action = tag.split(":", 1)[1]
                if self.on_action is not None:
                    self.on_action(action)
                return
