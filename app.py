"""Context Badge: a persistent, non-interactive Windows desktop overlay.

Step 1 deliberately has no third-party dependencies.  It observes the current
foreground top-level window and displays its application and title.
"""

from __future__ import annotations

import ctypes
import json
import os
import tkinter as tk
from ctypes import wintypes
from pathlib import Path
from tkinter import font as tkfont


if os.name != "nt":
    raise SystemExit("Context Badge currently supports Windows only.")


user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

# Make coordinates correct on scaled and multi-monitor displays.
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
except (AttributeError, OSError):
    user32.SetProcessDPIAware()


PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
GWL_EXSTYLE = -20
GWLP_HWNDPARENT = -8
WS_EX_TRANSPARENT = 0x00000020
WS_EX_TOOLWINDOW = 0x00000080
WS_EX_LAYERED = 0x00080000
WS_EX_NOACTIVATE = 0x08000000
HWND_TOPMOST = -1
SWP_NOSIZE = 0x0001
SWP_NOMOVE = 0x0002
SWP_NOACTIVATE = 0x0010
SWP_FRAMECHANGED = 0x0020
SWP_SHOWWINDOW = 0x0040
SW_SHOWNOACTIVATE = 4
MONITOR_DEFAULTTONEAREST = 0x00000002

CONFIG_PATH = Path(__file__).with_name(".context-badge.json")
DEFAULT_BACKGROUND = "#263244"
DEFAULT_TEXT = "#f4f7fb"
TRANSPARENT_KEY = "#010203"
COLOUR_PALETTE = (
    "#0f172a",
    "#263244",
    "#475569",
    "#94a3b8",
    "#f8fafc",
    "#facc15",
    "#f97316",
    "#ef4444",
    "#ec4899",
    "#8b5cf6",
    "#6366f1",
    "#2563eb",
    "#06b6d4",
    "#059669",
    "#84cc16",
    "#a16207",
)


def blend_hex(background: str, foreground: str, amount: float) -> str:
    """Blend two #RRGGBB colours; amount is the foreground proportion."""
    background_rgb = tuple(int(background[i : i + 2], 16) for i in (1, 3, 5))
    foreground_rgb = tuple(int(foreground[i : i + 2], 16) for i in (1, 3, 5))
    mixed = tuple(
        round(bg + (fg - bg) * amount)
        for bg, fg in zip(background_rgb, foreground_rgb)
    )
    return "#" + "".join(f"{channel:02x}" for channel in mixed)


def bounded_int(value: object, default: int, minimum: int, maximum: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    return max(minimum, min(maximum, parsed))


class RECT(ctypes.Structure):
    _fields_ = [
        ("left", wintypes.LONG),
        ("top", wintypes.LONG),
        ("right", wintypes.LONG),
        ("bottom", wintypes.LONG),
    ]


class MONITORINFO(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("rcMonitor", RECT),
        ("rcWork", RECT),
        ("dwFlags", wintypes.DWORD),
    ]


user32.GetForegroundWindow.restype = wintypes.HWND
user32.GetWindow.argtypes = [wintypes.HWND, wintypes.UINT]
user32.GetWindow.restype = wintypes.HWND
user32.GetParent.argtypes = [wintypes.HWND]
user32.GetParent.restype = wintypes.HWND
user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
user32.MonitorFromWindow.argtypes = [wintypes.HWND, wintypes.DWORD]
user32.MonitorFromWindow.restype = wintypes.HANDLE
user32.GetMonitorInfoW.argtypes = [wintypes.HANDLE, ctypes.POINTER(MONITORINFO)]
kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
kernel32.OpenProcess.restype = wintypes.HANDLE
kernel32.CloseHandle.argtypes = [wintypes.HANDLE]

SetWindowLongPtrW = getattr(user32, "SetWindowLongPtrW", user32.SetWindowLongW)
SetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_ssize_t]
SetWindowLongPtrW.restype = ctypes.c_ssize_t


FRIENDLY_APPS = {
    "code.exe": "Visual Studio Code",
    "chrome.exe": "Google Chrome",
    "msedge.exe": "Microsoft Edge",
    "firefox.exe": "Firefox",
    "windowsterminal.exe": "Terminal",
    "explorer.exe": "File Explorer",
    "notepad.exe": "Notepad",
    "obsidian.exe": "Obsidian",
}


def window_title(hwnd: int) -> str:
    length = user32.GetWindowTextLengthW(hwnd)
    if length <= 0:
        return "Untitled window"
    buffer = ctypes.create_unicode_buffer(length + 1)
    user32.GetWindowTextW(hwnd, buffer, length + 1)
    return buffer.value.strip() or "Untitled window"


def executable_name(hwnd: int) -> str:
    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid.value)
    if not handle:
        return "Application"
    try:
        size = wintypes.DWORD(32768)
        buffer = ctypes.create_unicode_buffer(size.value)
        if kernel32.QueryFullProcessImageNameW(handle, 0, buffer, ctypes.byref(size)):
            return os.path.basename(buffer.value)
    finally:
        kernel32.CloseHandle(handle)
    return "Application"


def friendly_app_name(executable: str) -> str:
    return FRIENDLY_APPS.get(executable.lower(), os.path.splitext(executable)[0].title())


def monitor_work_area(hwnd: int) -> RECT:
    monitor = user32.MonitorFromWindow(hwnd, MONITOR_DEFAULTTONEAREST)
    info = MONITORINFO(cbSize=ctypes.sizeof(MONITORINFO))
    if monitor and user32.GetMonitorInfoW(monitor, ctypes.byref(info)):
        return info.rcWork
    return RECT(0, 0, user32.GetSystemMetrics(0), user32.GetSystemMetrics(1))


class ContextBadge:
    DEFAULT_WIDTH = 440
    DEFAULT_HEIGHT = 72
    MIN_WIDTH = 280
    MIN_HEIGHT = 64
    MAX_WIDTH = 1000
    MAX_HEIGHT = 260
    EDIT_WIDTH = 44
    MAIN_MENU_WIDTH = 200
    COLOUR_MENU_WIDTH = 304
    MENU_ROW_HEIGHT = 42
    COLOUR_HEADER_HEIGHT = 38
    COLOUR_ROW_HEIGHT = 54
    TOP_MARGIN = 18
    POLL_MS = 200

    def __init__(self) -> None:
        self.config = self._load_config()
        self.background_color = self.config.get(
            "background_color", DEFAULT_BACKGROUND
        )
        self.text_color = self.config.get("text_color", DEFAULT_TEXT)
        self.secondary_text_color = blend_hex(
            self.background_color, self.text_color, 0.68
        )
        self.border_color = self.config.get(
            "border_color",
            blend_hex(self.background_color, self.text_color, 0.22),
        )
        self.background_transparent = bool(
            self.config.get("background_transparent", False)
        )
        self.badge_width = bounded_int(
            self.config.get("width"),
            self.DEFAULT_WIDTH,
            self.MIN_WIDTH,
            self.MAX_WIDTH,
        )
        self.badge_height = bounded_int(
            self.config.get("height"),
            self.DEFAULT_HEIGHT,
            self.MIN_HEIGHT,
            self.MAX_HEIGHT,
        )
        self.hover_color = blend_hex(self.background_color, self.text_color, 0.12)

        self.root = tk.Tk()
        self.root.title("Context Badge")
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        self.root.configure(bg=self.background_color)
        self.root.geometry(
            f"{self.badge_width}x{self.badge_height}"
            f"+{(self.root.winfo_screenwidth() - self.badge_width) // 2}"
            f"+{self.TOP_MARGIN}"
        )

        self.app_font = tkfont.Font(family="Segoe UI Semibold", size=10)
        self.title_font = tkfont.Font(family="Segoe UI Semibold", size=13)

        self.canvas = tk.Canvas(
            self.root,
            width=self.badge_width,
            height=self.badge_height,
            bg=self.background_color,
            highlightthickness=1,
            highlightbackground=self.border_color,
        )
        self.canvas.pack()
        self.app_text = self.canvas.create_text(
            22,
            19,
            anchor="w",
            fill=self.secondary_text_color,
            font=self.app_font,
            text="CONTEXT BADGE",
        )
        self.title_text = self.canvas.create_text(
            22,
            38,
            anchor="nw",
            width=self.badge_width - self.EDIT_WIDTH - 38,
            fill=self.text_color,
            font=self.title_font,
            text="Starting…",
        )
        self.resize_handle = self.canvas.create_text(
            self.badge_width - self.EDIT_WIDTH - 10,
            self.badge_height - 8,
            anchor="se",
            text="◢",
            fill="#69a7ff",
            font=("Segoe UI Symbol", 11),
            state="hidden",
        )

        # The edit control uses a separate native hit target overlaid inside the
        # badge. Visually it is one component; technically this keeps the body
        # click-through while the edit entry remains clickable.
        self.edit_window = tk.Toplevel(self.root)
        self.edit_window.title("Edit Context Badge")
        self.edit_window.overrideredirect(True)
        self.edit_window.attributes("-topmost", True)
        self.edit_window.configure(bg=self.background_color)
        self.edit_canvas = tk.Canvas(
            self.edit_window,
            width=self.EDIT_WIDTH,
            height=self.badge_height,
            bg=self.background_color,
            highlightthickness=0,
            cursor="hand2",
        )
        self.edit_canvas.pack()
        self.edit_button_bg = self.edit_canvas.create_oval(
            7,
            self.badge_height // 2 - 15,
            self.EDIT_WIDTH - 7,
            self.badge_height // 2 + 15,
            fill=self.background_color,
            outline=self.background_color,
        )
        self.edit_divider = self.edit_canvas.create_line(
            0, 10, 0, self.badge_height - 10, fill=self.border_color
        )
        self.edit_icon = self.edit_canvas.create_text(
            self.EDIT_WIDTH // 2,
            self.badge_height // 2,
            text="✎",
            fill=self.text_color,
            font=("Segoe UI Symbol", 13),
        )
        self.edit_canvas.bind("<Button-1>", lambda _event: self._toggle_edit_control())
        self.edit_canvas.bind(
            "<Enter>", lambda _event: self._set_edit_hover(True)
        )
        self.edit_canvas.bind(
            "<Leave>",
            lambda _event: self._set_edit_hover(False),
        )

        # The first level stays compact. All appearance controls live under the
        # Colours second-level page.
        self.edit_actions = [
            ("↔  Move badge", self._begin_move, "#f3f5f7"),
            ("◲  Resize badge", self._begin_resize, "#f3f5f7"),
            ("◉  Colours  ›", self._open_colours, "#f3f5f7"),
            ("×  Exit Context Badge", self._quit, "#ff8f8f"),
        ]
        self.menu_page = "main"
        self.menu_width = self.MAIN_MENU_WIDTH
        self.menu_height = self.MENU_ROW_HEIGHT * len(self.edit_actions)
        self.menu_window = tk.Toplevel(self.root)
        self.menu_window.title("Context Badge Edit Menu")
        self.menu_window.overrideredirect(True)
        self.menu_window.attributes("-topmost", True)
        self.menu_canvas = tk.Canvas(
            self.menu_window,
            width=self.menu_width,
            height=self.menu_height,
            bg="#20232a",
            highlightthickness=1,
            highlightbackground="#454b57",
            cursor="hand2",
        )
        self.menu_canvas.pack()
        self.menu_canvas.bind("<Button-1>", self._handle_menu_click)
        self._render_menu()

        # Tk creates a child drawing HWND inside a native top-level wrapper.
        # Extended window styles must be applied to the wrapper, otherwise the
        # child may become transparent to input while the actual window stays
        # hidden behind other applications.
        self.root.update_idletasks()
        tk_hwnd = self.root.winfo_id()
        self.overlay_hwnd = user32.GetParent(tk_hwnd) or tk_hwnd
        edit_tk_hwnd = self.edit_window.winfo_id()
        self.edit_hwnd = user32.GetParent(edit_tk_hwnd) or edit_tk_hwnd
        menu_tk_hwnd = self.menu_window.winfo_id()
        self.menu_hwnd = user32.GetParent(menu_tk_hwnd) or menu_tk_hwnd
        self.last_foreground = 0
        self.last_identity: tuple[str, str] | None = None
        self.current_app_name = "CONTEXT BADGE"
        self.current_title = "Starting…"
        self.move_mode = False
        self.resize_mode = False
        self.menu_open = False
        self.drag_offset = (0, 0)
        self.resize_origin = (0, 0, self.badge_width, self.badge_height)
        self.saved_position = self._load_position()
        self._attach_owned_overlays()
        self._set_click_through(True)
        self._make_edit_button_interactive()
        self._make_menu_interactive()
        self._apply_theme()
        self.canvas.bind("<ButtonPress-1>", self._start_drag)
        self.canvas.bind("<B1-Motion>", self._drag)
        self.canvas.bind("<ButtonRelease-1>", self._finish_drag)
        user32.ShowWindow(self.overlay_hwnd, SW_SHOWNOACTIVATE)
        user32.ShowWindow(self.edit_hwnd, SW_SHOWNOACTIVATE)
        self.menu_window.withdraw()
        if self.saved_position is not None:
            self._set_position(*self.saved_position)
        self.root.after(0, self.refresh)

    def _load_config(self) -> dict[str, object]:
        try:
            data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            return {}

    def _load_position(self) -> tuple[int, int] | None:
        try:
            return int(self.config["x"]), int(self.config["y"])
        except (ValueError, KeyError, TypeError):
            return None

    def _save_config(self) -> None:
        CONFIG_PATH.write_text(
            json.dumps(self.config, indent=2), encoding="utf-8"
        )

    def _save_position(self) -> None:
        x, y = self.root.winfo_x(), self.root.winfo_y()
        self.config.update(
            {
                "x": x,
                "y": y,
                "width": self.badge_width,
                "height": self.badge_height,
            }
        )
        self._save_config()
        self.saved_position = (x, y)

    def _set_click_through(self, enabled: bool) -> None:
        style = user32.GetWindowLongW(self.overlay_hwnd, GWL_EXSTYLE)
        style |= WS_EX_LAYERED | WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE
        if enabled:
            style |= WS_EX_TRANSPARENT
        else:
            style &= ~WS_EX_TRANSPARENT
        user32.SetWindowLongW(self.overlay_hwnd, GWL_EXSTYLE, style)
        user32.SetWindowPos(
            self.overlay_hwnd,
            HWND_TOPMOST,
            0,
            0,
            0,
            0,
            SWP_NOSIZE | SWP_NOMOVE | SWP_NOACTIVATE | SWP_FRAMECHANGED,
        )
        # Changing the body's extended style also changes its Z-order. Put the
        # embedded edit hit target back above the body immediately.
        if hasattr(self, "edit_hwnd"):
            self._raise_edit_control()

    def _attach_owned_overlays(self) -> None:
        # Tk does not preserve a native Win32 owner for overrideredirect
        # Toplevel windows. Explicit ownership is the durable Z-order rule we
        # need: owned edit/menu overlays are always drawn above the badge.
        SetWindowLongPtrW(self.edit_hwnd, GWLP_HWNDPARENT, self.overlay_hwnd)
        SetWindowLongPtrW(self.menu_hwnd, GWLP_HWNDPARENT, self.overlay_hwnd)

    def _make_edit_button_interactive(self) -> None:
        style = user32.GetWindowLongW(self.edit_hwnd, GWL_EXSTYLE)
        style |= WS_EX_LAYERED | WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE
        style &= ~WS_EX_TRANSPARENT
        user32.SetWindowLongW(self.edit_hwnd, GWL_EXSTYLE, style)
        user32.SetWindowPos(
            self.edit_hwnd,
            HWND_TOPMOST,
            0,
            0,
            0,
            0,
            SWP_NOSIZE | SWP_NOMOVE | SWP_NOACTIVATE | SWP_FRAMECHANGED,
        )

    def _raise_edit_control(self) -> None:
        user32.SetWindowPos(
            self.edit_hwnd,
            HWND_TOPMOST,
            0,
            0,
            0,
            0,
            SWP_NOSIZE | SWP_NOMOVE | SWP_NOACTIVATE | SWP_SHOWWINDOW,
        )
        if getattr(self, "menu_open", False):
            user32.SetWindowPos(
                self.menu_hwnd,
                HWND_TOPMOST,
                0,
                0,
                0,
                0,
                SWP_NOSIZE | SWP_NOMOVE | SWP_NOACTIVATE | SWP_SHOWWINDOW,
            )

    def _make_menu_interactive(self) -> None:
        style = user32.GetWindowLongW(self.menu_hwnd, GWL_EXSTYLE)
        style |= WS_EX_LAYERED | WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE
        style &= ~WS_EX_TRANSPARENT
        user32.SetWindowLongW(self.menu_hwnd, GWL_EXSTYLE, style)

    def _toggle_edit_control(self) -> None:
        if self.move_mode or self.resize_mode:
            self._end_interaction()
        else:
            if not self.menu_open:
                self.menu_page = "main"
                self._render_menu()
            self._set_menu_open(not self.menu_open)

    def _render_menu(self) -> None:
        self.menu_canvas.delete("all")
        if self.menu_page == "main":
            self.menu_width = self.MAIN_MENU_WIDTH
            self.menu_height = self.MENU_ROW_HEIGHT * len(self.edit_actions)
            self.menu_canvas.configure(
                width=self.menu_width, height=self.menu_height
            )
            for index, (label, _callback, colour) in enumerate(self.edit_actions):
                row_top = index * self.MENU_ROW_HEIGHT
                if index:
                    self.menu_canvas.create_line(
                        10,
                        row_top,
                        self.menu_width - 10,
                        row_top,
                        fill="#3b404b",
                    )
                self.menu_canvas.create_text(
                    16,
                    row_top + self.MENU_ROW_HEIGHT // 2,
                    anchor="w",
                    text=label,
                    fill=colour,
                    font=("Segoe UI Semibold", 11),
                )
        else:
            self._render_colour_menu()
        if hasattr(self, "overlay_hwnd"):
            self._set_position(self.root.winfo_x(), self.root.winfo_y())

    def _render_colour_menu(self) -> None:
        self.menu_width = self.COLOUR_MENU_WIDTH
        self.menu_height = self.COLOUR_HEADER_HEIGHT + self.COLOUR_ROW_HEIGHT * 3
        self.menu_canvas.configure(width=self.menu_width, height=self.menu_height)
        self.menu_canvas.create_text(
            14,
            self.COLOUR_HEADER_HEIGHT // 2,
            anchor="w",
            text="‹  Colours",
            fill="#aab3c2",
            font=("Segoe UI Semibold", 10),
        )
        self.menu_canvas.create_line(
            10,
            self.COLOUR_HEADER_HEIGHT,
            self.menu_width - 10,
            self.COLOUR_HEADER_HEIGHT,
            fill="#3b404b",
        )

        properties = (
            ("Background", "background_color", self.background_color),
            ("Text", "text_color", self.text_color),
            ("Border", "border_color", self.border_color),
        )
        swatch_x = 106
        swatch_size = 17
        swatch_gap = 5
        for row, (label, _key, selected) in enumerate(properties):
            row_top = self.COLOUR_HEADER_HEIGHT + row * self.COLOUR_ROW_HEIGHT
            self.menu_canvas.create_text(
                14,
                row_top + self.COLOUR_ROW_HEIGHT // 2,
                anchor="w",
                text=label,
                fill="#f3f5f7",
                font=("Segoe UI", 10),
            )
            if row == 0:
                transparent_outline = (
                    "#ffffff" if self.background_transparent else "#596170"
                )
                self.menu_canvas.create_rectangle(
                    80,
                    row_top + 18,
                    97,
                    row_top + 35,
                    fill="#20232a",
                    outline=transparent_outline,
                    width=2 if self.background_transparent else 1,
                )
                self.menu_canvas.create_line(
                    82,
                    row_top + 33,
                    95,
                    row_top + 20,
                    fill="#ff8f8f",
                    width=2,
                )
            for index, colour in enumerate(COLOUR_PALETTE):
                column = index % 8
                palette_row = index // 8
                x1 = swatch_x + column * (swatch_size + swatch_gap)
                y1 = row_top + 6 + palette_row * (swatch_size + swatch_gap)
                outline = "#ffffff" if colour.lower() == str(selected).lower() else "#596170"
                width = 2 if colour.lower() == str(selected).lower() else 1
                self.menu_canvas.create_rectangle(
                    x1,
                    y1,
                    x1 + swatch_size,
                    y1 + swatch_size,
                    fill=colour,
                    outline=outline,
                    width=width,
                )

    def _open_colours(self) -> None:
        self.menu_page = "colours"
        self._render_menu()

    def _handle_menu_click(self, event: tk.Event) -> None:
        if self.menu_page == "main":
            index = event.y // self.MENU_ROW_HEIGHT
            if 0 <= index < len(self.edit_actions):
                self.edit_actions[index][1]()
            return

        if event.y < self.COLOUR_HEADER_HEIGHT:
            self.menu_page = "main"
            self._render_menu()
            return

        row = (event.y - self.COLOUR_HEADER_HEIGHT) // self.COLOUR_ROW_HEIGHT
        local_y = (event.y - self.COLOUR_HEADER_HEIGHT) % self.COLOUR_ROW_HEIGHT
        if not 0 <= row < 3:
            return
        if row == 0 and 80 <= event.x <= 97 and 18 <= local_y <= 35:
            self.background_transparent = True
            self.config["background_transparent"] = True
            self._apply_theme()
            self._save_config()
            self._render_menu()
            return

        swatch_x = 106
        step = 22
        column = (event.x - swatch_x) // step
        palette_row = (local_y - 6) // step
        within_x = 0 <= (event.x - swatch_x) % step <= 17
        within_y = 0 <= (local_y - 6) % step <= 17
        swatch = palette_row * 8 + column
        if (
            0 <= column < 8
            and 0 <= palette_row < 2
            and within_x
            and within_y
            and 0 <= swatch < len(COLOUR_PALETTE)
        ):
            key = ("background_color", "text_color", "border_color")[row]
            if key == "background_color":
                self.background_transparent = False
                self.config["background_transparent"] = False
            self._set_colour(key, COLOUR_PALETTE[swatch])

    def _set_menu_open(self, open_: bool) -> None:
        self.menu_open = open_
        if open_:
            self.menu_window.deiconify()
            # Some Tk builds recreate native state while deiconifying.
            self._attach_owned_overlays()
            user32.ShowWindow(self.menu_hwnd, SW_SHOWNOACTIVATE)
            self.menu_window.lift()
        else:
            self.menu_window.withdraw()
        self._update_edit_icon()
        self._raise_edit_control()

    def _begin_move(self) -> None:
        self._set_menu_open(False)
        self.move_mode = True
        self.resize_mode = False
        self._set_click_through(False)
        # A fully transparent body has no draggable pixels, so move mode
        # temporarily reveals the selected background colour.
        self._apply_theme()
        self.canvas.configure(cursor="fleur")
        self._update_app_label()

    def _begin_resize(self) -> None:
        self._set_menu_open(False)
        self.move_mode = False
        self.resize_mode = True
        self._set_click_through(False)
        self._apply_theme()
        self.canvas.configure(cursor="sizing")
        self.canvas.itemconfigure(self.resize_handle, state="normal")
        self._update_app_label()

    def _set_colour(self, key: str, selected: str) -> None:
        attribute = {
            "background_color": "background_color",
            "text_color": "text_color",
            "border_color": "border_color",
        }[key]
        setattr(self, attribute, selected)
        self.config[key] = selected
        self._apply_theme()
        self._save_config()
        self._render_menu()

    def _apply_theme(self) -> None:
        self.secondary_text_color = blend_hex(
            self.background_color, self.text_color, 0.68
        )
        self.hover_color = blend_hex(self.background_color, self.text_color, 0.12)
        transparent_now = (
            self.background_transparent
            and not self.move_mode
            and not self.resize_mode
        )
        body_colour = TRANSPARENT_KEY if transparent_now else self.background_color
        self.root.attributes(
            "-transparentcolor", TRANSPARENT_KEY if transparent_now else ""
        )
        self.root.configure(bg=body_colour)
        self.canvas.configure(
            bg=body_colour,
            highlightbackground="#69a7ff" if self.move_mode else self.border_color,
        )
        self.canvas.itemconfigure(self.app_text, fill=self.secondary_text_color)
        self.canvas.itemconfigure(self.title_text, fill=self.text_color)
        self.edit_window.attributes(
            "-transparentcolor", TRANSPARENT_KEY if transparent_now else ""
        )
        edit_body_colour = TRANSPARENT_KEY if transparent_now else self.background_color
        self.edit_window.configure(bg=edit_body_colour)
        self.edit_canvas.configure(bg=edit_body_colour)
        button_fill = self.hover_color if transparent_now else self.background_color
        button_outline = self.border_color if transparent_now else self.background_color
        self.edit_canvas.itemconfigure(
            self.edit_button_bg, fill=button_fill, outline=button_outline
        )
        self.edit_canvas.itemconfigure(self.edit_divider, fill=self.border_color)
        self._update_edit_icon()

    def _set_edit_hover(self, hovered: bool) -> None:
        transparent_now = (
            self.background_transparent
            and not self.move_mode
            and not self.resize_mode
        )
        if transparent_now:
            fill = (
                blend_hex(self.background_color, self.text_color, 0.24)
                if hovered
                else self.hover_color
            )
            self.edit_canvas.itemconfigure(self.edit_button_bg, fill=fill)
        else:
            self.edit_canvas.configure(
                bg=self.hover_color if hovered else self.background_color
            )

    def _quit(self) -> None:
        if self.move_mode or self.resize_mode:
            self._save_position()
        self.root.destroy()

    def _end_interaction(self) -> None:
        self._save_position()
        self.move_mode = False
        self.resize_mode = False
        self._apply_theme()
        self._set_click_through(True)
        self.canvas.configure(cursor="")
        self.canvas.itemconfigure(self.resize_handle, state="hidden")
        self._update_app_label()

    def _update_edit_icon(self) -> None:
        editing = self.move_mode or self.resize_mode
        icon = "✓" if editing else ("×" if self.menu_open else "✎")
        active = editing or self.menu_open
        self.edit_canvas.itemconfigure(
            self.edit_icon,
            text=icon,
            fill="#8fc0ff" if active else self.text_color,
        )
        self._raise_edit_control()

    def _update_app_label(self) -> None:
        if self.move_mode:
            prefix = "MOVE MODE · "
        elif self.resize_mode:
            prefix = "RESIZE MODE · "
        else:
            prefix = ""
        self._render_text(prefix + self.current_app_name, self.current_title)

    @staticmethod
    def _fit_text(
        text: str, font: tkfont.Font, max_width: int, max_lines: int
    ) -> str:
        """Wrap by measured pixels and ellipsize without crossing its region."""
        if max_width <= 0 or max_lines <= 0:
            return ""
        lines: list[str] = []
        current = ""
        overflowed = False
        for character in text.replace("\r", ""):
            if character == "\n":
                lines.append(current.rstrip())
                current = ""
            elif not current or font.measure(current + character) <= max_width:
                current += character
            else:
                lines.append(current.rstrip())
                current = character.lstrip()
            if len(lines) >= max_lines:
                overflowed = bool(current) or character != text[-1:]
                break
        else:
            if current or not lines:
                lines.append(current.rstrip())

        if len(lines) > max_lines:
            lines = lines[:max_lines]
            overflowed = True
        if overflowed:
            last = lines[-1] if lines else ""
            while last and font.measure(last + "…") > max_width:
                last = last[:-1]
            if not last and font.measure("…") > max_width:
                return ""
            if lines:
                lines[-1] = last.rstrip() + "…"
            else:
                lines = ["…"]
        return "\n".join(lines)

    def _render_text(self, app_label: str, title: str) -> None:
        available_width = max(80, self.badge_width - self.EDIT_WIDTH - 44)
        app_display = self._fit_text(app_label, self.app_font, available_width, 1)
        line_height = max(1, self.title_font.metrics("linespace"))
        available_height = max(line_height, self.badge_height - 44)
        max_lines = max(1, available_height // line_height)
        title_display = self._fit_text(
            title, self.title_font, available_width, max_lines
        )
        self.canvas.itemconfigure(self.app_text, text=app_display)
        self.canvas.itemconfigure(
            self.title_text, text=title_display, width=available_width
        )

    def _set_badge_size(self, width: int, height: int) -> None:
        self.badge_width = int(width)
        self.badge_height = int(height)
        self.canvas.configure(width=self.badge_width, height=self.badge_height)
        self.canvas.coords(
            self.resize_handle,
            self.badge_width - self.EDIT_WIDTH - 10,
            self.badge_height - 8,
        )
        self.edit_canvas.configure(width=self.EDIT_WIDTH, height=self.badge_height)
        self.edit_canvas.coords(
            self.edit_button_bg,
            7,
            self.badge_height // 2 - 15,
            self.EDIT_WIDTH - 7,
            self.badge_height // 2 + 15,
        )
        self.edit_canvas.coords(
            self.edit_divider, 0, 10, 0, self.badge_height - 10
        )
        self.edit_canvas.coords(
            self.edit_icon, self.EDIT_WIDTH // 2, self.badge_height // 2
        )
        self._set_position(self.root.winfo_x(), self.root.winfo_y())
        self._update_app_label()

    def _start_drag(self, event: tk.Event) -> None:
        if self.move_mode:
            self.drag_offset = (
                event.x_root - self.root.winfo_x(),
                event.y_root - self.root.winfo_y(),
            )
        elif self.resize_mode:
            self.resize_origin = (
                event.x_root,
                event.y_root,
                self.badge_width,
                self.badge_height,
            )

    def _drag(self, event: tk.Event) -> None:
        if not self.move_mode:
            if not self.resize_mode:
                return
            start_x, start_y, start_width, start_height = self.resize_origin
            width = max(
                self.MIN_WIDTH,
                min(self.MAX_WIDTH, start_width + event.x_root - start_x),
            )
            height = max(
                self.MIN_HEIGHT,
                min(self.MAX_HEIGHT, start_height + event.y_root - start_y),
            )
            self._set_badge_size(width, height)
        else:
            x = event.x_root - self.drag_offset[0]
            y = event.y_root - self.drag_offset[1]
            self.saved_position = (x, y)
            self._set_position(x, y)

    def _finish_drag(self, _event: tk.Event) -> None:
        if self.move_mode or self.resize_mode:
            self._save_position()

    def _set_position(self, x: int, y: int) -> None:
        self.root.geometry(f"{self.badge_width}x{self.badge_height}+{x}+{y}")
        user32.SetWindowPos(
            self.overlay_hwnd,
            HWND_TOPMOST,
            x,
            y,
            0,
            0,
            SWP_NOSIZE | SWP_NOACTIVATE | SWP_SHOWWINDOW,
        )
        edit_x = x + self.badge_width - self.EDIT_WIDTH
        edit_y = y
        self.edit_window.geometry(
            f"{self.EDIT_WIDTH}x{self.badge_height}+{edit_x}+{edit_y}"
        )
        user32.SetWindowPos(
            self.edit_hwnd,
            HWND_TOPMOST,
            edit_x,
            edit_y,
            0,
            0,
            SWP_NOSIZE | SWP_NOACTIVATE | SWP_SHOWWINDOW,
        )
        menu_x = x + self.badge_width - self.menu_width
        menu_y = y + self.badge_height + 6
        self.menu_window.geometry(
            f"{self.menu_width}x{self.menu_height}+{menu_x}+{menu_y}"
        )
        if self.menu_open:
            user32.SetWindowPos(
                self.menu_hwnd,
                HWND_TOPMOST,
                menu_x,
                menu_y,
                0,
                0,
                SWP_NOSIZE | SWP_NOACTIVATE | SWP_SHOWWINDOW,
            )

    def _move_to_active_monitor(self, foreground: int) -> None:
        if self.saved_position is not None:
            self._set_position(*self.saved_position)
            return
        work = monitor_work_area(foreground)
        x = work.left + ((work.right - work.left) - self.badge_width) // 2
        y = work.top + self.TOP_MARGIN
        self._set_position(x, y)

    def refresh(self) -> None:
        foreground = user32.GetForegroundWindow()
        if foreground and foreground not in (
            self.overlay_hwnd,
            self.edit_hwnd,
            self.menu_hwnd,
        ):
            self.last_foreground = foreground
        else:
            foreground = self.last_foreground

        if foreground:
            executable = executable_name(foreground)
            title = window_title(foreground)
            identity = (executable, title)
            if identity != self.last_identity:
                self.current_app_name = friendly_app_name(executable).upper()
                self.current_title = title
                self._update_app_label()
                self.last_identity = identity
            self._move_to_active_monitor(foreground)

        self.root.after(self.POLL_MS, self.refresh)

    def run(self) -> None:
        try:
            self.root.mainloop()
        except KeyboardInterrupt:
            # Ctrl+C is the Step 1 exit mechanism. Avoid printing a traceback.
            self.root.destroy()


if __name__ == "__main__":
    ContextBadge().run()
