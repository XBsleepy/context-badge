"""Standalone rounded menu popup, kept separate so it can grow new pages."""

from __future__ import annotations

import tkinter as tk
from collections.abc import Callable, Sequence

from .bubble import draw_rounded_panel
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
ROW_HEIGHT = 40
HEADER_HEIGHT = 36
SECTION_HEIGHT = 22
THEME_CARD_H = 52
PILL_H = 28
SWATCH_ROW_H = 48
PAD = 14
INSET = 2


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
    ) -> None:
        self.on_action = on_action
        self.on_theme = on_theme
        self.on_colour = on_colour
        self.on_radius = on_radius
        self.on_pet_action = on_pet_action
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
        user32.ShowWindow(self.hwnd, SW_HIDE)
        self.window.withdraw()

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
        if self.page == "appearance":
            self._render_appearance()
        elif self.page == "pet":
            self._render_pet()
        else:
            self._render_main()
        if self.open:
            self._place()

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
            if tag.startswith("action:"):
                self.on_action(tag.split(":", 1)[1])
                return
            if tag.startswith("petaction:"):
                action = tag.split(":", 1)[1]
                if self.on_pet_action is not None:
                    self.on_pet_action(action)
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
