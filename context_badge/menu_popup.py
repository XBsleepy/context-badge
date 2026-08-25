"""Standalone rounded menu popup, kept separate so it can grow new pages."""

from __future__ import annotations

import tkinter as tk
from collections.abc import Callable, Sequence

from .bubble import draw_rounded_panel
from .rest_timer import (
    CUSTOM_REST_SLOTS,
    PRESET_REST_MINUTES,
    custom_slot_is_selected,
    format_rest_interval,
    normalize_custom_minutes,
    normalize_custom_slot,
    normalize_rest_alert_style,
    normalize_rest_message,
    normalize_rest_minutes,
)
from .theme import (
    COLOUR_PALETTE,
    COLOUR_THEMES,
    RADIUS_CHOICES,
    TRANSPARENT,
    TRANSPARENT_KEY,
    is_transparent,
    matching_theme_id,
    paint_color,
)
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

MAIN_WIDTH = 228
APPEARANCE_WIDTH = 304
PET_WIDTH = 228
REST_WIDTH = 260
HIDE_WIDTH = 240
ROW_HEIGHT = 40
HEADER_HEIGHT = 36
SECTION_HEIGHT = 22
THEME_CARD_H = 52
PILL_H = 28
SWATCH_ROW_H = 48
PAD = 14
INSET = 2

HIDE_TARGETS = ("badge", "pet", "all")
HIDE_TARGET_LABELS = {
    "badge": "Badge",
    "pet": "Pet",
    "all": "All",
}


def normalize_hide_target(value: object) -> str:
    text = str(value or "all").strip().lower()
    if text in HIDE_TARGETS:
        return text
    return "all"


class MenuPopup:
    """A topmost rounded flyout owned by the badge."""

    def __init__(
        self,
        parent: tk.Misc,
        *,
        on_action: Callable[[str], None],
        on_theme: Callable[[str], None],
        on_colour: Callable[[str, str], None],
        on_radius: Callable[[int], None],
        on_pet_action: Callable[[str], None] | None = None,
        on_rest_action: Callable[[str], None] | None = None,
        on_rest_minutes: Callable[[int, int | None], None] | None = None,
        on_rest_custom: Callable[[int, int | None], None] | None = None,
        on_rest_message: Callable[[str], None] | None = None,
        on_rest_alert: Callable[[str], None] | None = None,
        on_hide_target: Callable[[str], None] | None = None,
    ) -> None:
        self.on_action = on_action
        self.on_theme = on_theme
        self.on_colour = on_colour
        self.on_radius = on_radius
        self.on_pet_action = on_pet_action
        self.on_rest_action = on_rest_action
        self.on_rest_minutes = on_rest_minutes
        self.on_rest_custom = on_rest_custom
        self.on_rest_message = on_rest_message
        self.on_rest_alert = on_rest_alert
        self.on_hide_target = on_hide_target
        self.page = "main"
        self.open = False
        self._right = 0
        self._y = 0
        self.width = MAIN_WIDTH
        self.height = 180
        self._radius = 12
        self._fill = "#101218"
        self._text = "#f4f1ea"
        self._muted = "#aab3c2"
        self._border = "#8a8175"
        self._background = "#16181d"
        self._list_background = "#101218"
        self._rest_enabled = False
        self._rest_paused = False
        self._rest_minutes = 60
        self._rest_custom_slot: int | None = None
        self._custom_minutes: list[int | None] = [None] * CUSTOM_REST_SLOTS
        self._rest_entries: list[tk.Entry] = []
        self._message_entry: tk.Entry | None = None
        self._rest_message = "Time to rest"
        self._rest_alert = "pet"
        self._preset_panels: dict[int, int] = {}
        self._preset_labels: dict[int, int] = {}
        self._custom_panels: list[int] = []
        self._committing_custom = False
        self._hide_target = "all"
        self._actions: list[tuple[str, str]] = []

        self.window = tk.Toplevel(parent)
        self.window.title("Context Badge menu")
        self.window.overrideredirect(True)
        self.window.attributes("-topmost", True)
        self.window.configure(bg=TRANSPARENT_KEY)
        self.window.attributes("-transparentcolor", TRANSPARENT_KEY)
        self.canvas = tk.Canvas(
            self.window,
            width=self.width,
            height=self.height,
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

    def _apply_window_style(self, *, activate: bool = False) -> None:
        style = user32.GetWindowLongW(self.hwnd, GWL_EXSTYLE)
        style |= WS_EX_LAYERED | WS_EX_TOOLWINDOW
        style &= ~WS_EX_TRANSPARENT
        if activate:
            style &= ~WS_EX_NOACTIVATE
        else:
            style |= WS_EX_NOACTIVATE
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
        list_background: str,
    ) -> None:
        self._fill = paint_color(fill, "#101218")
        if is_transparent(fill):
            self._fill = paint_color(background, "#16181d")
        self._text = text
        self._muted = muted
        self._border = border
        self._radius = max(0, int(radius))
        self._background = background
        self._list_background = list_background
        if self._custom_focused():
            return
        self._render()

    def set_rest_state(
        self,
        *,
        enabled: bool,
        paused: bool,
        minutes: int,
        custom_minutes: Sequence[int | None] | None = None,
        custom_slot: int | None = None,
        message: str | None = None,
        alert_style: str | None = None,
    ) -> None:
        self._rest_enabled = bool(enabled)
        self._rest_paused = bool(paused)
        self._rest_minutes = normalize_rest_minutes(minutes)
        if custom_minutes is not None:
            self._custom_minutes = normalize_custom_minutes(list(custom_minutes))
        self._rest_custom_slot = normalize_custom_slot(
            custom_slot,
            self._custom_minutes,
            self._rest_minutes,
        )
        if message is not None:
            self._rest_message = normalize_rest_message(message)
        if alert_style is not None:
            self._rest_alert = normalize_rest_alert_style(alert_style)
        if self.page != "rest":
            return
        if self._custom_focused():
            self._refresh_interval_highlights()
            return
        self._render()

    def set_hide_target(self, target: str) -> None:
        self._hide_target = normalize_hide_target(target)
        if self.page == "hide":
            self._render()

    def set_actions(self, actions: Sequence[tuple[str, str]]) -> None:
        self._actions = [(str(key), str(label)) for key, label in actions]
        if self.page == "main":
            self._render()

    def show(self) -> None:
        self.open = True
        self._render()
        self.window.deiconify()
        self._apply_window_style()
        user32.ShowWindow(self.hwnd, SW_SHOWNOACTIVATE)
        self.window.lift()
        self._place()

    def hide(self) -> None:
        self.open = False
        self.page = "main"
        self._clear_rest_entries()
        user32.ShowWindow(self.hwnd, SW_HIDE)
        self.window.withdraw()
        self._apply_window_style(activate=False)

    def set_position(self, x: int, y: int) -> None:
        self._y = int(y)
        self._right = int(x) + self.width
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
        left = self._right - self.width
        self.window.geometry(f"{self.width}x{self.height}+{left}+{self._y}")
        user32.SetWindowPos(
            self.hwnd,
            HWND_TOPMOST,
            left,
            self._y,
            self.width,
            self.height,
            SWP_NOACTIVATE | SWP_SHOWWINDOW,
        )

    def _active_theme(self) -> str | None:
        return matching_theme_id(
            self._background,
            self._list_background,
            self._text,
            self._border,
        )

    def _render(self) -> None:
        self._clear_rest_entries()
        if self.page == "appearance":
            self._render_appearance()
        elif self.page == "pet":
            self._render_pet()
        elif self.page == "rest":
            self._render_rest()
        elif self.page == "hide":
            self._render_hide()
        else:
            self._render_main()
        self._apply_window_style(activate=self.page == "rest")
        if self.open:
            self._place()

    def _clear_rest_entries(self) -> None:
        for entry in self._rest_entries:
            try:
                entry.destroy()
            except tk.TclError:
                pass
        self._rest_entries = []
        self._preset_panels = {}
        self._preset_labels = {}
        self._custom_panels = []
        if self._message_entry is not None:
            try:
                self._message_entry.destroy()
            except tk.TclError:
                pass
            self._message_entry = None

    def _custom_focused(self) -> bool:
        try:
            focus = self.window.focus_get()
        except tk.TclError:
            return False
        return focus in self._rest_entries or focus is self._message_entry

    def _paint_card(self) -> None:
        self.canvas.delete("all")
        self.canvas.configure(width=self.width, height=self.height)
        draw_rounded_panel(
            self.canvas,
            INSET,
            INSET,
            self.width - INSET,
            self.height - INSET,
            fill=self._fill,
            outline=self._border,
            radius=self._radius,
            width=2,
            tags="chrome",
        )

    def _render_main(self) -> None:
        rows = list(self._actions)
        keys = {key for key, _label in rows}
        insert_at = max(0, len(rows) - 1)
        if "appearance" not in keys:
            rows.insert(insert_at, ("appearance", "Appearance  ›"))
            insert_at += 1
        if "pet" not in keys:
            rows.insert(insert_at, ("pet", "Pet  ›"))
            insert_at += 1
        if "rest" not in keys:
            rows.insert(insert_at, ("rest", "Break  ›"))
            insert_at += 1
        if "hide" not in keys:
            rows.insert(insert_at, ("hide", "Hide  ›"))
        self.width = MAIN_WIDTH
        self.height = HEADER_HEIGHT + ROW_HEIGHT * max(1, len(rows)) + PAD
        self._paint_card()
        self.canvas.create_text(
            PAD + 2,
            HEADER_HEIGHT // 2 + 4,
            anchor="w",
            text="Menu",
            fill=self._muted,
            font=("Segoe UI Semibold", 10),
            tags="chrome",
        )
        for index, (key, label) in enumerate(rows):
            top = HEADER_HEIGHT + index * ROW_HEIGHT
            tag = f"action:{key}"
            if index:
                self.canvas.create_line(
                    PAD,
                    top,
                    self.width - PAD,
                    top,
                    fill=self._border,
                    tags="chrome",
                )
            self.canvas.create_rectangle(
                INSET + 4,
                top + 2,
                self.width - INSET - 4,
                top + ROW_HEIGHT - 2,
                fill=self._fill,
                outline=self._fill,
                tags=tag,
            )
            self.canvas.create_text(
                PAD + 2,
                top + ROW_HEIGHT // 2,
                anchor="w",
                text=label,
                fill=self._text,
                font=("Segoe UI Semibold", 11),
                tags=tag,
            )

    def _render_appearance(self) -> None:
        theme_rows = (len(COLOUR_THEMES) + 2) // 3
        colour_rows = 4
        self.width = APPEARANCE_WIDTH
        self.height = (
            HEADER_HEIGHT
            + SECTION_HEIGHT
            + theme_rows * THEME_CARD_H
            + 8
            + SECTION_HEIGHT
            + PILL_H
            + 10
            + SECTION_HEIGHT
            + colour_rows * SWATCH_ROW_H
            + PAD
        )
        self._paint_card()
        self.canvas.create_rectangle(
            INSET + 4,
            6,
            90,
            HEADER_HEIGHT - 2,
            fill=self._fill,
            outline=self._fill,
            tags="back",
        )
        self.canvas.create_text(
            PAD,
            HEADER_HEIGHT // 2 + 2,
            anchor="w",
            text="‹  Appearance",
            fill=self._muted,
            font=("Segoe UI Semibold", 10),
            tags="back",
        )
        y = HEADER_HEIGHT
        y = self._section(y, "Themes")
        y = self._draw_themes(y)
        y += 8
        y = self._section(y, "Corners")
        y = self._draw_radius_pills(y)
        y += 10
        y = self._section(y, "Colours")
        self._draw_colour_rows(y)

    def _render_pet(self) -> None:
        rows = (("place", "Place"), ("size", "Size"))
        self.width = PET_WIDTH
        self.height = HEADER_HEIGHT + ROW_HEIGHT * len(rows) + 28 + PAD
        self._paint_card()
        self.canvas.create_rectangle(
            INSET + 4,
            6,
            70,
            HEADER_HEIGHT - 2,
            fill=self._fill,
            outline=self._fill,
            tags="back",
        )
        self.canvas.create_text(
            PAD,
            HEADER_HEIGHT // 2 + 2,
            anchor="w",
            text="‹  Pet",
            fill=self._muted,
            font=("Segoe UI Semibold", 10),
            tags="back",
        )
        for index, (key, label) in enumerate(rows):
            top = HEADER_HEIGHT + index * ROW_HEIGHT
            tag = f"petaction:{key}"
            if index:
                self.canvas.create_line(
                    PAD,
                    top,
                    self.width - PAD,
                    top,
                    fill=self._border,
                    tags="chrome",
                )
            self.canvas.create_rectangle(
                INSET + 4,
                top + 2,
                self.width - INSET - 4,
                top + ROW_HEIGHT - 2,
                fill=self._fill,
                outline=self._fill,
                tags=tag,
            )
            self.canvas.create_text(
                PAD + 2,
                top + ROW_HEIGHT // 2,
                anchor="w",
                text=label,
                fill=self._text,
                font=("Segoe UI Semibold", 11),
                tags=tag,
            )
        hint_y = HEADER_HEIGHT + ROW_HEIGHT * len(rows) + 10
        self.canvas.create_text(
            PAD + 2,
            hint_y,
            anchor="w",
            text="Then drag the pet",
            fill=self._muted,
            font=("Segoe UI", 9),
            tags="chrome",
        )

    def _render_rest(self) -> None:
        self.width = REST_WIDTH
        self.height = (
            HEADER_HEIGHT
            + SECTION_HEIGHT
            + PILL_H
            + 10
            + SECTION_HEIGHT
            + 2 * (PILL_H + 6)
            + 18
            + SECTION_HEIGHT
            + PILL_H
            + 10
            + SECTION_HEIGHT
            + PILL_H
            + PAD
        )
        self._paint_card()
        self.canvas.create_rectangle(
            INSET + 4,
            6,
            86,
            HEADER_HEIGHT - 2,
            fill=self._fill,
            outline=self._fill,
            tags="back",
        )
        self.canvas.create_text(
            PAD,
            HEADER_HEIGHT // 2 + 2,
            anchor="w",
            text="‹  Break",
            fill=self._muted,
            font=("Segoe UI Semibold", 10),
            tags="back",
        )
        y = self._section(HEADER_HEIGHT, "Timer")
        y = self._draw_rest_mode_pills(y)
        y += 10
        y = self._section(y, "Every")
        y = self._draw_rest_interval_pills(y)
        y += 16
        y = self._section(y, "Alert")
        y = self._draw_rest_alert_pills(y)
        y += 10
        y = self._section(y, "Message")
        self._draw_rest_message_field(y)

    def _render_hide(self) -> None:
        self.width = HIDE_WIDTH
        self.height = HEADER_HEIGHT + SECTION_HEIGHT + PILL_H + 28 + PAD
        self._paint_card()
        self.canvas.create_rectangle(
            INSET + 4,
            6,
            78,
            HEADER_HEIGHT - 2,
            fill=self._fill,
            outline=self._fill,
            tags="back",
        )
        self.canvas.create_text(
            PAD,
            HEADER_HEIGHT // 2 + 2,
            anchor="w",
            text="‹  Hide",
            fill=self._muted,
            font=("Segoe UI Semibold", 10),
            tags="back",
        )
        y = self._section(HEADER_HEIGHT, "Hide tab hides")
        self._draw_hide_target_pills(y)
        self.canvas.create_text(
            PAD,
            HEADER_HEIGHT + SECTION_HEIGHT + PILL_H + 12,
            anchor="w",
            text="Badge · Pet · All (taskbar)",
            fill=self._muted,
            font=("Segoe UI", 9),
            tags="chrome",
        )

    def _draw_hide_target_pills(self, y: int) -> int:
        gap = 6
        pills = tuple(
            (key, HIDE_TARGET_LABELS[key], self._hide_target == key)
            for key in HIDE_TARGETS
        )
        count = len(pills)
        pill_w = (self.width - 2 * PAD - gap * (count - 1)) // count
        for index, (key, label, chosen) in enumerate(pills):
            x1 = PAD + index * (pill_w + gap)
            x2 = x1 + pill_w
            y2 = y + PILL_H
            tag = f"hidetarget:{key}"
            draw_rounded_panel(
                self.canvas,
                x1,
                y,
                x2,
                y2,
                fill=self._text if chosen else self._fill,
                outline=self._border,
                radius=min(12, PILL_H // 2),
                width=1,
                tags=tag,
            )
            self.canvas.create_text(
                (x1 + x2) // 2,
                (y + y2) // 2,
                text=label,
                fill=self._fill if chosen else self._text,
                font=("Segoe UI Semibold", 9),
                tags=tag,
            )
        return y + PILL_H

    def _draw_rest_mode_pills(self, y: int) -> int:
        gap = 6
        pills = (
            ("on", "On", self._rest_enabled and not self._rest_paused),
            ("paused", "Paused", self._rest_enabled and self._rest_paused),
            ("off", "Off", not self._rest_enabled),
        )
        count = len(pills)
        pill_w = (self.width - 2 * PAD - gap * (count - 1)) // count
        for index, (key, label, chosen) in enumerate(pills):
            x1 = PAD + index * (pill_w + gap)
            x2 = x1 + pill_w
            y2 = y + PILL_H
            tag = f"restmode:{key}"
            draw_rounded_panel(
                self.canvas,
                x1,
                y,
                x2,
                y2,
                fill=self._text if chosen else self._fill,
                outline=self._border,
                radius=min(12, PILL_H // 2),
                width=1,
                tags=tag,
            )
            self.canvas.create_text(
                (x1 + x2) // 2,
                (y + y2) // 2,
                text=label,
                fill=self._fill if chosen else self._text,
                font=("Segoe UI Semibold", 9),
                tags=tag,
            )
        return y + PILL_H

    def _draw_rest_alert_pills(self, y: int) -> int:
        gap = 6
        pills = (
            ("pet", "Pet", self._rest_alert == "pet"),
            ("window", "Window", self._rest_alert == "window"),
        )
        count = len(pills)
        pill_w = (self.width - 2 * PAD - gap * (count - 1)) // count
        for index, (key, label, chosen) in enumerate(pills):
            x1 = PAD + index * (pill_w + gap)
            x2 = x1 + pill_w
            y2 = y + PILL_H
            tag = f"restalert:{key}"
            draw_rounded_panel(
                self.canvas,
                x1,
                y,
                x2,
                y2,
                fill=self._text if chosen else self._fill,
                outline=self._border,
                radius=min(12, PILL_H // 2),
                width=1,
                tags=tag,
            )
            self.canvas.create_text(
                (x1 + x2) // 2,
                (y + y2) // 2,
                text=label,
                fill=self._fill if chosen else self._text,
                font=("Segoe UI Semibold", 9),
                tags=tag,
            )
        return y + PILL_H

    def _draw_rest_interval_pills(self, y: int) -> int:
        gap = 6
        cols = 3
        pill_w = (self.width - 2 * PAD - gap * (cols - 1)) // cols
        self._preset_panels = {}
        self._preset_labels = {}
        self._custom_panels = []
        for index, value in enumerate(PRESET_REST_MINUTES):
            column = index % cols
            x1 = PAD + column * (pill_w + gap)
            x2 = x1 + pill_w
            y2 = y + PILL_H
            tag = f"restmin:{value}"
            chosen = self._preset_chosen(value)
            panel = draw_rounded_panel(
                self.canvas,
                x1,
                y,
                x2,
                y2,
                fill=self._text if chosen else self._fill,
                outline=self._border,
                radius=min(12, PILL_H // 2),
                width=1,
                tags=tag,
            )
            label = self.canvas.create_text(
                (x1 + x2) // 2,
                (y + y2) // 2,
                text=format_rest_interval(value * 60),
                fill=self._fill if chosen else self._text,
                font=("Segoe UI Semibold", 9),
                tags=tag,
            )
            self._preset_panels[value] = panel
            self._preset_labels[value] = label
        custom_y = y + PILL_H + gap
        for index in range(CUSTOM_REST_SLOTS):
            x1 = PAD + index * (pill_w + gap)
            x2 = x1 + pill_w
            y2 = custom_y + PILL_H
            minutes = self._custom_minutes[index]
            chosen = self._custom_chosen(index)
            panel = draw_rounded_panel(
                self.canvas,
                x1,
                custom_y,
                x2,
                y2,
                fill=self._text if chosen else self._fill,
                outline=self._border,
                radius=min(12, PILL_H // 2),
                width=1,
                tags=f"restcustom:{index}",
            )
            self._custom_panels.append(panel)
            entry = tk.Entry(
                self.canvas,
                justify="center",
                bd=0,
                highlightthickness=0,
                relief="flat",
                font=("Segoe UI Semibold", 9),
                bg=self._text if chosen else self._fill,
                fg=self._fill if chosen else self._text,
                insertbackground=self._fill if chosen else self._text,
                width=4,
            )
            if minutes is not None:
                entry.insert(0, str(minutes))
            entry.bind(
                "<KeyPress>",
                lambda event, field=entry: self._on_custom_key(event, field),
            )
            entry.bind(
                "<Return>",
                lambda _event, slot=index, field=entry: self._commit_custom(
                    slot, field
                ),
            )
            entry.bind(
                "<KP_Enter>",
                lambda _event, slot=index, field=entry: self._commit_custom(
                    slot, field
                ),
            )
            entry.bind(
                "<FocusIn>",
                lambda _event, slot=index: self._on_custom_focus(slot),
            )
            entry.bind(
                "<FocusOut>",
                lambda _event, slot=index, field=entry: self._commit_custom(
                    slot, field, select=False
                ),
            )
            self.canvas.create_window(
                (x1 + x2) // 2,
                (custom_y + y2) // 2,
                window=entry,
                width=max(28, pill_w - 10),
                height=PILL_H - 8,
            )
            self._rest_entries.append(entry)
        return custom_y + PILL_H

    def _draw_rest_message_field(self, y: int) -> int:
        x1 = PAD
        x2 = self.width - PAD
        y2 = y + PILL_H
        draw_rounded_panel(
            self.canvas,
            x1,
            y,
            x2,
            y2,
            fill=self._fill,
            outline=self._border,
            radius=min(12, PILL_H // 2),
            width=1,
            tags="chrome",
        )
        entry = tk.Entry(
            self.canvas,
            bd=0,
            highlightthickness=0,
            relief="flat",
            font=("Segoe UI", 9),
            bg=self._fill,
            fg=self._text,
            insertbackground=self._text,
        )
        entry.insert(0, self._rest_message)
        entry.bind("<Return>", lambda _event, field=entry: self._commit_message(field))
        entry.bind("<KP_Enter>", lambda _event, field=entry: self._commit_message(field))
        entry.bind(
            "<FocusOut>",
            lambda _event, field=entry: self._commit_message(field),
        )
        self.canvas.create_window(
            (x1 + x2) // 2,
            (y + y2) // 2,
            window=entry,
            width=max(40, x2 - x1 - 12),
            height=PILL_H - 8,
        )
        self._message_entry = entry
        return y2

    def _commit_message(self, field: tk.Entry) -> str:
        message = normalize_rest_message(field.get())
        self._rest_message = message
        try:
            if field.get() != message:
                field.delete(0, "end")
                field.insert(0, message)
        except tk.TclError:
            pass
        if self.on_rest_message is not None:
            self.on_rest_message(message)
        return "break"

    def _preset_chosen(self, value: int) -> bool:
        return (
            self._rest_custom_slot is None and self._rest_minutes == value
        )

    def _custom_chosen(self, slot: int) -> bool:
        return custom_slot_is_selected(
            slot,
            minutes=self._rest_minutes,
            customs=self._custom_minutes,
            selected_slot=self._rest_custom_slot,
        )

    def _refresh_interval_highlights(self) -> None:
        for value, panel in self._preset_panels.items():
            chosen = self._preset_chosen(value)
            try:
                self.canvas.itemconfigure(
                    panel,
                    fill=self._text if chosen else self._fill,
                )
                self.canvas.itemconfigure(
                    self._preset_labels[value],
                    fill=self._fill if chosen else self._text,
                )
            except tk.TclError:
                pass
        for index, panel in enumerate(self._custom_panels):
            chosen = self._custom_chosen(index)
            try:
                self.canvas.itemconfigure(
                    panel,
                    fill=self._text if chosen else self._fill,
                )
            except tk.TclError:
                pass
            if index >= len(self._rest_entries):
                continue
            entry = self._rest_entries[index]
            try:
                entry.configure(
                    bg=self._text if chosen else self._fill,
                    fg=self._fill if chosen else self._text,
                    insertbackground=self._fill if chosen else self._text,
                )
            except tk.TclError:
                pass

    def _emit_rest_minutes(self, minutes: int, custom_slot: int | None) -> None:
        self._rest_minutes = normalize_rest_minutes(minutes)
        self._rest_custom_slot = custom_slot
        self._refresh_interval_highlights()
        if self.on_rest_minutes is not None:
            self.on_rest_minutes(self._rest_minutes, custom_slot)

    def _on_custom_key(self, event: tk.Event, field: tk.Entry) -> str | None:
        if event.keysym in (
            "BackSpace",
            "Delete",
            "Left",
            "Right",
            "Home",
            "End",
            "Tab",
            "Return",
            "KP_Enter",
            "Escape",
        ):
            return None
        if event.char and event.char.isdigit():
            selected = bool(field.selection_present())
            if not selected and len(field.get()) >= 3:
                return "break"
            return None
        if event.char:
            return "break"
        return None

    def _parse_custom_field(self, field: tk.Entry) -> int | None:
        text = field.get().strip()
        if not text:
            return None
        try:
            minutes = int(text)
        except ValueError:
            return None
        if minutes <= 0:
            return None
        return normalize_rest_minutes(minutes)

    def _on_custom_focus(self, slot: int) -> None:
        minutes = self._custom_minutes[slot]
        if minutes is None:
            return
        self._emit_rest_minutes(minutes, slot)

    def _commit_custom(
        self,
        slot: int,
        field: tk.Entry,
        *,
        select: bool = True,
    ) -> str:
        if self._committing_custom:
            return "break"
        self._committing_custom = True
        try:
            minutes = self._parse_custom_field(field)
            if minutes is None:
                try:
                    field.delete(0, "end")
                except tk.TclError:
                    pass
            self._custom_minutes[slot] = minutes
            if self.on_rest_custom is not None:
                self.on_rest_custom(slot, minutes)
            if select and minutes is not None:
                self._emit_rest_minutes(minutes, slot)
                try:
                    self.canvas.focus_set()
                except tk.TclError:
                    pass
                self._render()
            else:
                if self._rest_custom_slot == slot and minutes is None:
                    self._rest_custom_slot = None
                self._refresh_interval_highlights()
        finally:
            self._committing_custom = False
        return "break"

    def _section(self, y: int, title: str) -> int:
        self.canvas.create_text(
            PAD,
            y + 12,
            anchor="w",
            text=title,
            fill=self._muted,
            font=("Segoe UI Semibold", 9),
        )
        return y + SECTION_HEIGHT

    def _draw_themes(self, y: int) -> int:
        cols = 3
        gap = 8
        card_w = (self.width - 2 * PAD - gap * (cols - 1)) // cols
        active = self._active_theme()
        for index, theme in enumerate(COLOUR_THEMES):
            column = index % cols
            row = index // cols
            x1 = PAD + column * (card_w + gap)
            y1 = y + row * THEME_CARD_H
            x2 = x1 + card_w
            y2 = y1 + THEME_CARD_H - 8
            tag = f"theme:{theme.id}"
            chosen = theme.id == active
            draw_rounded_panel(
                self.canvas,
                x1,
                y1,
                x2,
                y2,
                fill=theme.background,
                outline=self._text if chosen else theme.border,
                radius=10,
                width=2 if chosen else 1,
                tags=tag,
            )
            self.canvas.create_rectangle(
                x1 + 6,
                y2 - 11,
                x2 - 6,
                y2 - 6,
                fill=theme.list_background,
                outline=theme.list_background,
                tags=tag,
            )
            self.canvas.create_text(
                x1 + 8,
                y1 + 12,
                anchor="w",
                text=theme.name,
                fill=theme.text,
                font=("Segoe UI Semibold", 9),
                tags=tag,
            )
        rows = (len(COLOUR_THEMES) + cols - 1) // cols
        return y + rows * THEME_CARD_H

    def _draw_radius_pills(self, y: int) -> int:
        gap = 6
        count = len(RADIUS_CHOICES)
        pill_w = (self.width - 2 * PAD - gap * (count - 1)) // count
        for index, value in enumerate(RADIUS_CHOICES):
            x1 = PAD + index * (pill_w + gap)
            x2 = x1 + pill_w
            y2 = y + PILL_H
            tag = f"radius:{value}"
            chosen = int(self._radius) == int(value)
            draw_rounded_panel(
                self.canvas,
                x1,
                y,
                x2,
                y2,
                fill=self._text if chosen else self._fill,
                outline=self._border,
                radius=min(12, PILL_H // 2),
                width=1,
                tags=tag,
            )
            self.canvas.create_text(
                (x1 + x2) // 2,
                (y + y2) // 2,
                text=str(value),
                fill=self._fill if chosen else self._text,
                font=("Segoe UI Semibold", 9),
                tags=tag,
            )
        return y + PILL_H

    def _draw_colour_rows(self, y: int) -> None:
        rows = (
            ("Background", "background_color", self._background, True),
            ("List", "list_background_color", self._list_background, True),
            ("Text", "text_color", self._text, False),
            ("Border", "border_color", self._border, False),
        )
        size = 14
        gap = 4
        origin_x = 78
        per_line = 8
        for row, (label, key, selected, allow_clear) in enumerate(rows):
            top = y + row * SWATCH_ROW_H
            self.canvas.create_text(
                PAD,
                top + 14,
                anchor="w",
                text=label,
                fill=self._text,
                font=("Segoe UI", 9),
            )
            x = origin_x
            line_y = top + 6
            if allow_clear:
                tag = f"colour:{key}:{TRANSPARENT}"
                chosen = is_transparent(selected)
                self.canvas.create_oval(
                    x,
                    line_y,
                    x + size,
                    line_y + size,
                    fill=self._fill,
                    outline=self._text if chosen else self._border,
                    width=2 if chosen else 1,
                    tags=tag,
                )
                self.canvas.create_line(
                    x + 3,
                    line_y + size - 3,
                    x + size - 3,
                    line_y + 3,
                    fill="#ff8f8f",
                    width=2,
                    tags=tag,
                )
                x += size + gap + 2
            palette_x = x
            for index, colour in enumerate(COLOUR_PALETTE):
                if index and index % per_line == 0:
                    x = palette_x
                    line_y += size + 4
                tag = f"colour:{key}:{colour}"
                chosen = (
                    not is_transparent(selected)
                    and str(selected).lower() == colour.lower()
                )
                self.canvas.create_oval(
                    x,
                    line_y,
                    x + size,
                    line_y + size,
                    fill=colour,
                    outline=self._text if chosen else self._border,
                    width=2 if chosen else 1,
                    tags=tag,
                )
                x += size + gap

    def _on_click(self, event: tk.Event) -> None:
        items = self.canvas.find_overlapping(event.x, event.y, event.x, event.y)
        tags: list[str] = []
        for item in reversed(items):
            tags.extend(str(tag) for tag in self.canvas.gettags(item))
        for tag in tags:
            if tag == "back":
                self.page = "main"
                self._render()
                return
            if tag == "action:appearance":
                self.page = "appearance"
                self._render()
                return
            if tag == "action:pet":
                self.page = "pet"
                self._render()
                return
            if tag == "action:rest":
                self.page = "rest"
                self._render()
                return
            if tag == "action:hide":
                self.page = "hide"
                self._render()
                return
            if tag.startswith("action:"):
                self.on_action(tag.split(":", 1)[1])
                return
            if tag.startswith("petaction:"):
                action = tag.split(":", 1)[1]
                if self.on_pet_action is not None:
                    self.on_pet_action(action)
                return
            if tag.startswith("restmode:"):
                mode = tag.split(":", 1)[1]
                if self.on_rest_action is not None:
                    self.on_rest_action(mode)
                return
            if tag.startswith("restalert:"):
                style = normalize_rest_alert_style(tag.split(":", 1)[1])
                self._rest_alert = style
                if self.on_rest_alert is not None:
                    self.on_rest_alert(style)
                self._render()
                return
            if tag.startswith("restsec:") or tag.startswith("restmin:"):
                minutes = normalize_rest_minutes(tag.split(":", 1)[1])
                self._emit_rest_minutes(minutes, None)
                self._render()
                return
            if tag.startswith("restcustom:"):
                slot = int(tag.split(":", 1)[1])
                stored = self._custom_minutes[slot]
                if stored is not None:
                    self._emit_rest_minutes(stored, slot)
                    self._refresh_interval_highlights()
                return
            if tag.startswith("hidetarget:"):
                target = normalize_hide_target(tag.split(":", 1)[1])
                self._hide_target = target
                if self.on_hide_target is not None:
                    self.on_hide_target(target)
                self._render()
                return
            if tag.startswith("theme:"):
                self.on_theme(tag.split(":", 1)[1])
                return
            if tag.startswith("radius:"):
                self.on_radius(int(tag.split(":", 1)[1]))
                return
            if tag.startswith("colour:"):
                _prefix, key, value = tag.split(":", 2)
                self.on_colour(key, value)
                return
