"""Speech-bubble rest reminder anchored beside the pet."""

from __future__ import annotations

import tkinter as tk
import tkinter.font as tkfont
from collections.abc import Callable

from .bubble import draw_rounded_panel, draw_speech_bubble
from .rest_timer import (
    DEFAULT_RESTING_NOTICE,
    format_rest_interval,
    normalize_rest_alert_style,
    normalize_rest_message,
)
from .text_layout import fit_text
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
    monitor_work_area_from_point,
    clamp_into,
    virtual_screen,
    user32,
)

TOAST_WIDTH = 228
TOAST_HEIGHT = 118
TAIL = 12
PAD = 14
INSET = 2


class PetToast:
    """A pet-side message bubble shown when the rest timer fires."""

    def __init__(
        self,
        parent: tk.Misc,
        *,
        on_action: Callable[[str], None] | None = None,
    ) -> None:
        self.on_action = on_action
        self.open = False
        self._pet_x = 0
        self._pet_y = 0
        self._pet_w = 0
        self._pet_h = 0
        self._fill = "#101218"
        self._text = "#f4f1ea"
        self._muted = "#aab3c2"
        self._border = "#8a8175"
        self._radius = 12
        self._message = "Time to rest"
        self._interval_seconds = 3600
        self._mode = "alarm"
        self._style = "pet"
        self._tail_side = "left"
        self._font = tkfont.Font(parent, family="Segoe UI Semibold", size=11)
        self._muted_font = tkfont.Font(parent, family="Segoe UI", size=9)

        self.window = tk.Toplevel(parent)
        self.window.title("Rest message")
        self.window.overrideredirect(True)
        self.window.attributes("-topmost", True)
        self.window.configure(bg=TRANSPARENT_KEY)
        self.window.attributes("-transparentcolor", TRANSPARENT_KEY)
        self.canvas = tk.Canvas(
            self.window,
            width=TOAST_WIDTH,
            height=TOAST_HEIGHT,
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

    def set_content(
        self,
        *,
        message: str,
        interval_seconds: int,
        mode: str = "alarm",
    ) -> None:
        self._message = normalize_rest_message(message)
        self._interval_seconds = int(interval_seconds)
        self._mode = "resting" if mode == "resting" else "alarm"
        if self.open:
            self._render()

    def show_beside(
        self,
        pet_x: int,
        pet_y: int,
        pet_w: int,
        pet_h: int,
        *,
        style: str = "pet",
    ) -> None:
        self._pet_x = int(pet_x)
        self._pet_y = int(pet_y)
        self._pet_w = max(0, int(pet_w))
        self._pet_h = max(0, int(pet_h))
        self._style = normalize_rest_alert_style(style)
        self.open = True
        self._choose_side()
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

    def set_pet_rect(self, pet_x: int, pet_y: int, pet_w: int, pet_h: int) -> None:
        self._pet_x = int(pet_x)
        self._pet_y = int(pet_y)
        self._pet_w = max(0, int(pet_w))
        self._pet_h = max(0, int(pet_h))
        if self.open:
            self._choose_side()
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

    def _choose_side(self) -> None:
        if self._style == "window":
            self._tail_side = "none"
            return
        work = monitor_work_area_from_point(
            self._pet_x + self._pet_w // 2,
            self._pet_y + self._pet_h // 2,
        )
        right_left = self._pet_x + self._pet_w + 6
        if right_left + TOAST_WIDTH <= work.right - 8:
            self._tail_side = "left"
            return
        self._tail_side = "right"

    def _place(self) -> None:
        work = monitor_work_area_from_point(
            self._pet_x + self._pet_w // 2,
            self._pet_y + self._pet_h // 2,
        )
        if self._style == "window":
            left = work.left + ((work.right - work.left) - TOAST_WIDTH) // 2
            top = work.top + max(48, ((work.bottom - work.top) - TOAST_HEIGHT) // 3)
        elif self._tail_side == "left":
            left = self._pet_x + self._pet_w + 6
            top = self._pet_y + max(0, (self._pet_h - TOAST_HEIGHT) // 2)
        else:
            left = self._pet_x - TOAST_WIDTH - 6
            top = self._pet_y + max(0, (self._pet_h - TOAST_HEIGHT) // 2)
        left, top = clamp_into(
            left,
            top,
            TOAST_WIDTH,
            TOAST_HEIGHT,
            virtual_screen(),
        )
        self.window.geometry(f"{TOAST_WIDTH}x{TOAST_HEIGHT}+{left}+{top}")
        user32.SetWindowPos(
            self.hwnd,
            HWND_TOPMOST,
            left,
            top,
            TOAST_WIDTH,
            TOAST_HEIGHT,
            SWP_NOACTIVATE | SWP_SHOWWINDOW,
        )

    def _render(self) -> None:
        self.canvas.delete("all")
        self.canvas.configure(width=TOAST_WIDTH, height=TOAST_HEIGHT)
        if self._style == "window":
            draw_rounded_panel(
                self.canvas,
                INSET,
                INSET,
                TOAST_WIDTH - INSET,
                TOAST_HEIGHT - INSET,
                fill=self._fill,
                outline=self._border,
                radius=self._radius,
                width=2,
                tags="chrome",
            )
            text_left = PAD
            text_right = TOAST_WIDTH - PAD
        else:
            draw_speech_bubble(
                self.canvas,
                TOAST_WIDTH,
                TOAST_HEIGHT,
                fill=self._fill,
                outline=self._border,
                radius=self._radius,
                tail_side=self._tail_side,
                tail_size=TAIL,
                inset=INSET,
                tags="chrome",
            )
            text_left = PAD + (TAIL if self._tail_side == "left" else 0)
            text_right = TOAST_WIDTH - PAD - (TAIL if self._tail_side == "right" else 0)
        text_width = max(40, text_right - text_left)
        if self._mode == "resting":
            body = DEFAULT_RESTING_NOTICE
            subtitle = "Timer waits until you Ack"
        else:
            body = self._message
            subtitle = f"Every {format_rest_interval(self._interval_seconds)}"
        wrapped = fit_text(body, self._font, text_width, 3)
        self.canvas.create_text(
            text_left,
            18,
            anchor="nw",
            text=wrapped,
            fill=self._text,
            font=self._font,
            width=text_width,
            tags="chrome",
        )
        self.canvas.create_text(
            text_left,
            72,
            anchor="w",
            text=subtitle,
            fill=self._muted,
            font=self._muted_font,
            tags="chrome",
        )
        btn_y1 = TOAST_HEIGHT - 32
        btn_y2 = TOAST_HEIGHT - 12
        mid = (text_left + text_right) // 2
        if self._mode == "resting":
            self._pill(text_left, btn_y1, text_right, btn_y2, "ack", "Ack")
        else:
            self._pill(text_left, btn_y1, mid - 4, btn_y2, "rest", "Rest")
            self._pill(mid + 4, btn_y1, text_right, btn_y2, "pause", "Pause")

    def _pill(
        self,
        x1: int,
        y1: int,
        x2: int,
        y2: int,
        action: str,
        label: str,
    ) -> None:
        tag = f"toast:{action}"
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
            if tag.startswith("toast:"):
                action = tag.split(":", 1)[1]
                if self.on_action is not None:
                    self.on_action(action)
                return
