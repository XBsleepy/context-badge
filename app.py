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
from tkinter import colorchooser


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


def blend_hex(background: str, foreground: str, amount: float) -> str:
    """Blend two #RRGGBB colours; amount is the foreground proportion."""
    background_rgb = tuple(int(background[i : i + 2], 16) for i in (1, 3, 5))
    foreground_rgb = tuple(int(foreground[i : i + 2], 16) for i in (1, 3, 5))
    mixed = tuple(
        round(bg + (fg - bg) * amount)
        for bg, fg in zip(background_rgb, foreground_rgb)
    )
    return "#" + "".join(f"{channel:02x}" for channel in mixed)


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
    WIDTH = 440
    HEIGHT = 72
    EDIT_WIDTH = 44
    MENU_WIDTH = 184
    MENU_ROW_HEIGHT = 42
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
        self.border_color = blend_hex(self.background_color, self.text_color, 0.22)
        self.hover_color = blend_hex(self.background_color, self.text_color, 0.12)

        self.root = tk.Tk()
        self.root.title("Context Badge")
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        self.root.configure(bg=self.background_color)
        self.root.geometry(
            f"{self.WIDTH}x{self.HEIGHT}"
            f"+{(self.root.winfo_screenwidth() - self.WIDTH) // 2}"
            f"+{self.TOP_MARGIN}"
        )

        self.canvas = tk.Canvas(
            self.root,
            width=self.WIDTH,
            height=self.HEIGHT,
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
            font=("Segoe UI Semibold", 10),
            text="CONTEXT BADGE",
        )
        self.title_text = self.canvas.create_text(
            22,
            47,
            anchor="w",
            width=self.WIDTH - self.EDIT_WIDTH - 38,
            fill=self.text_color,
            font=("Segoe UI Semibold", 13),
            text="Starting…",
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
            height=self.HEIGHT,
            bg=self.background_color,
            highlightthickness=0,
            cursor="hand2",
        )
        self.edit_canvas.pack()
        self.edit_divider = self.edit_canvas.create_line(
            0, 10, 0, self.HEIGHT - 10, fill=self.border_color
        )
        self.edit_icon = self.edit_canvas.create_text(
            self.EDIT_WIDTH // 2,
            self.HEIGHT // 2,
            text="✎",
            fill=self.text_color,
            font=("Segoe UI Symbol", 13),
        )
        self.edit_canvas.bind("<Button-1>", lambda _event: self._toggle_edit_control())
        self.edit_canvas.bind(
            "<Enter>", lambda _event: self.edit_canvas.configure(bg=self.hover_color)
        )
        self.edit_canvas.bind(
            "<Leave>",
            lambda _event: self.edit_canvas.configure(bg=self.background_color),
        )

        # This popover is intentionally action-based so future edit operations
        # (rename context, choose colour, add a rule) can be appended here.
        self.edit_actions = [
            ("↔  Move badge", self._begin_move, "#f3f5f7"),
            ("▣  Background colour", self._choose_background, "#f3f5f7"),
            ("A  Text colour", self._choose_text, "#f3f5f7"),
            ("×  Exit Context Badge", self._quit, "#ff8f8f"),
        ]
        self.menu_height = self.MENU_ROW_HEIGHT * len(self.edit_actions)
        self.menu_window = tk.Toplevel(self.root)
        self.menu_window.title("Context Badge Edit Menu")
        self.menu_window.overrideredirect(True)
        self.menu_window.attributes("-topmost", True)
        self.menu_canvas = tk.Canvas(
            self.menu_window,
            width=self.MENU_WIDTH,
            height=self.menu_height,
            bg="#20232a",
            highlightthickness=1,
            highlightbackground="#454b57",
            cursor="hand2",
        )
        self.menu_canvas.pack()
        for index, (label, _callback, colour) in enumerate(self.edit_actions):
            row_top = index * self.MENU_ROW_HEIGHT
            if index:
                self.menu_canvas.create_line(
                    10,
                    row_top,
                    self.MENU_WIDTH - 10,
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
        self.menu_canvas.bind("<Button-1>", self._run_edit_action)

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
        self.move_mode = False
        self.menu_open = False
        self.drag_offset = (0, 0)
        self.saved_position = self._load_position()
        self._attach_owned_overlays()
        self._set_click_through(True)
        self._make_edit_button_interactive()
        self._make_menu_interactive()
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
        self.config.update({"x": x, "y": y})
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
        if self.move_mode:
            self._end_move()
        else:
            self._set_menu_open(not self.menu_open)

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
        self._set_click_through(False)
        self.canvas.configure(highlightbackground="#69a7ff", cursor="fleur")
        self._update_edit_icon()
        self._update_app_label()

    def _choose_background(self) -> None:
        self._choose_colour("background_color", "Choose badge background colour")

    def _choose_text(self) -> None:
        self._choose_colour("text_color", "Choose badge text colour")

    def _choose_colour(self, key: str, title: str) -> None:
        self._set_menu_open(False)
        current = self.background_color if key == "background_color" else self.text_color
        selected = colorchooser.askcolor(
            color=current, title=title, parent=self.root
        )[1]
        if not selected:
            return
        if key == "background_color":
            self.background_color = selected
        else:
            self.text_color = selected
        self.config[key] = selected
        self._apply_theme()
        self._save_config()

    def _apply_theme(self) -> None:
        self.secondary_text_color = blend_hex(
            self.background_color, self.text_color, 0.68
        )
        self.border_color = blend_hex(self.background_color, self.text_color, 0.22)
        self.hover_color = blend_hex(self.background_color, self.text_color, 0.12)
        self.root.configure(bg=self.background_color)
        self.canvas.configure(
            bg=self.background_color,
            highlightbackground="#69a7ff" if self.move_mode else self.border_color,
        )
        self.canvas.itemconfigure(self.app_text, fill=self.secondary_text_color)
        self.canvas.itemconfigure(self.title_text, fill=self.text_color)
        self.edit_window.configure(bg=self.background_color)
        self.edit_canvas.configure(bg=self.background_color)
        self.edit_canvas.itemconfigure(self.edit_divider, fill=self.border_color)
        self._update_edit_icon()

    def _run_edit_action(self, event: tk.Event) -> None:
        index = event.y // self.MENU_ROW_HEIGHT
        if 0 <= index < len(self.edit_actions):
            self.edit_actions[index][1]()

    def _quit(self) -> None:
        if self.move_mode:
            self._save_position()
        self.root.destroy()

    def _end_move(self) -> None:
        self._save_position()
        self.move_mode = False
        self._set_click_through(True)
        self.canvas.configure(highlightbackground=self.border_color, cursor="")
        self._update_edit_icon()
        self._update_app_label()

    def _update_edit_icon(self) -> None:
        icon = "✓" if self.move_mode else ("×" if self.menu_open else "✎")
        active = self.move_mode or self.menu_open
        self.edit_canvas.itemconfigure(
            self.edit_icon,
            text=icon,
            fill="#8fc0ff" if active else self.text_color,
        )
        self._raise_edit_control()

    def _update_app_label(self) -> None:
        prefix = "MOVE MODE · " if self.move_mode else ""
        self.canvas.itemconfigure(self.app_text, text=prefix + self.current_app_name)

    def _start_drag(self, event: tk.Event) -> None:
        if self.move_mode:
            self.drag_offset = (
                event.x_root - self.root.winfo_x(),
                event.y_root - self.root.winfo_y(),
            )

    def _drag(self, event: tk.Event) -> None:
        if not self.move_mode:
            return
        x = event.x_root - self.drag_offset[0]
        y = event.y_root - self.drag_offset[1]
        self.saved_position = (x, y)
        self._set_position(x, y)

    def _finish_drag(self, _event: tk.Event) -> None:
        if self.move_mode:
            self._save_position()

    def _set_position(self, x: int, y: int) -> None:
        self.root.geometry(f"{self.WIDTH}x{self.HEIGHT}+{x}+{y}")
        user32.SetWindowPos(
            self.overlay_hwnd,
            HWND_TOPMOST,
            x,
            y,
            0,
            0,
            SWP_NOSIZE | SWP_NOACTIVATE | SWP_SHOWWINDOW,
        )
        edit_x = x + self.WIDTH - self.EDIT_WIDTH
        edit_y = y
        self.edit_window.geometry(
            f"{self.EDIT_WIDTH}x{self.HEIGHT}+{edit_x}+{edit_y}"
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
        menu_x = x + self.WIDTH - self.MENU_WIDTH
        menu_y = y + self.HEIGHT + 6
        self.menu_window.geometry(
            f"{self.MENU_WIDTH}x{self.menu_height}+{menu_x}+{menu_y}"
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
        x = work.left + ((work.right - work.left) - self.WIDTH) // 2
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
                self._update_app_label()
                self.canvas.itemconfigure(self.title_text, text=title)
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
