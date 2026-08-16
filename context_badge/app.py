"""Context Badge: a persistent, non-interactive Windows desktop overlay.

Step 1 deliberately has no third-party dependencies.  It observes the current
foreground top-level window and displays its application and title.
"""

from __future__ import annotations

import atexit
import json
import tkinter as tk
from tkinter import font as tkfont

from .analysis_window import AnalysisWindow
from .dwell import (
    DEFAULT_CHECKPOINT_SECONDS,
    DEFAULT_NOISE_SECONDS,
    MAX_CHECKPOINT_SECONDS,
    MAX_NOISE_SECONDS,
    MIN_CHECKPOINT_SECONDS,
    MIN_NOISE_SECONDS,
    DwellObservation,
    DwellTracker,
)
from .dwell_store import DwellStore
from .layout import badge_metrics
from .list_bar import GAP_FROM_BADGE, ListBar
from .list_store import ListStore
from .paths import config_path, dwell_active_path, dwell_log_path, lists_path
from .surface import surface_label
from .text_layout import fit_text
from .theme import (
    COLOUR_PALETTE,
    DEFAULT_BACKGROUND,
    DEFAULT_TEXT,
    TRANSPARENT_KEY,
    blend_hex,
    bounded_int,
)
from .win32 import (
    GWL_EXSTYLE,
    GWLP_HWNDPARENT,
    HWND_TOPMOST,
    SWP_FRAMECHANGED,
    SWP_NOACTIVATE,
    SWP_NOMOVE,
    SWP_NOSIZE,
    SWP_SHOWWINDOW,
    SW_HIDE,
    SW_SHOWNOACTIVATE,
    WS_EX_APPWINDOW,
    WS_EX_LAYERED,
    WS_EX_NOACTIVATE,
    WS_EX_TOOLWINDOW,
    WS_EX_TRANSPARENT,
    executable_name,
    friendly_app_name,
    monitor_work_area,
    root_hwnd,
    set_window_owner,
    user32,
    window_title,
)

class ContextBadge:
    DEFAULT_WIDTH = 440
    DEFAULT_HEIGHT = 72
    MIN_WIDTH = 280
    MIN_HEIGHT = 64
    MAX_WIDTH = 1000
    MAX_HEIGHT = 260
    TAB_COUNT = 4
    TAB_WIDTH = 46
    EDIT_WIDTH = TAB_COUNT * TAB_WIDTH
    MAIN_MENU_WIDTH = 200
    COLOUR_MENU_WIDTH = 304
    MENU_ROW_HEIGHT = 42
    COLOUR_HEADER_HEIGHT = 38
    COLOUR_ROW_HEIGHT = 54
    TOP_MARGIN = 18
    POLL_MS = 200
    LONG_PRESS_MS = 400
    DRAG_THRESHOLD_PX = 8

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
        self.minimized = False
        self._suppress_taskbar_map = False
        self.hovered_tab: int | None = None
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
        self._ensure_dwell_config()
        self._ensure_list_bar_config()
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

        self.layout = badge_metrics(self.badge_width, self.badge_height)
        self.app_font = tkfont.Font(
            family="Segoe UI Semibold", size=self.layout.app_font_size
        )
        self.title_font = tkfont.Font(
            family="Segoe UI Semibold", size=self.layout.title_font_size
        )
        self.handle_font = tkfont.Font(
            family="Segoe UI Symbol", size=self.layout.handle_font_size
        )
        self.edit_icon_font = tkfont.Font(
            family="Segoe UI Symbol", size=self.layout.edit_icon_font_size
        )
        self.tab_label_font = tkfont.Font(
            family="Segoe UI",
            size=max(7, min(9, self.layout.app_font_size - 2)),
        )

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
            self.layout.padding_x,
            self.layout.app_y,
            anchor="w",
            fill=self.secondary_text_color,
            font=self.app_font,
            text="CONTEXT BADGE",
        )
        self.title_text = self.canvas.create_text(
            self.layout.padding_x,
            self.layout.title_y,
            anchor="nw",
            width=self.badge_width - self.EDIT_WIDTH - self.layout.padding_x
            - self.layout.text_right_gap,
            fill=self.text_color,
            font=self.title_font,
            text="Starting…",
        )
        self.resize_handle = self.canvas.create_text(
            self.badge_width - self.EDIT_WIDTH - self.layout.handle_inset_x,
            self.badge_height - self.layout.handle_inset_y,
            anchor="se",
            text="◢",
            fill="#69a7ff",
            font=self.handle_font,
            state="hidden",
        )

        # The control strip is a separate native hit target overlaid on the
        # right edge. The badge body stays click-through; these three tabs
        # remain clickable.
        self.edit_window = tk.Toplevel(self.root)
        self.edit_window.title("Context Badge controls")
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
        self.edit_canvas.bind("<ButtonPress-1>", self._handle_control_press)
        self.edit_canvas.bind("<B1-Motion>", self._handle_control_drag)
        self.edit_canvas.bind("<ButtonRelease-1>", self._handle_control_release)
        self.edit_canvas.bind("<Motion>", self._on_control_motion)
        self.edit_canvas.bind("<Leave>", self._on_control_leave)

        # The first level stays compact. All appearance controls live under the
        # Colours second-level page. Close lives on the control strip. Move is
        # a long-press on Menu rather than a menu row.
        self.edit_actions = [
            ("◲  Resize badge", self._begin_resize, "#f3f5f7"),
            ("◉  Colours  ›", self._open_colours, "#f3f5f7"),
            ("◷  Time analysis", self._open_analysis, "#f3f5f7"),
        ]
        self.menu_page = "main"
        self.menu_width = self.MAIN_MENU_WIDTH
        self.menu_height = self.MENU_ROW_HEIGHT * len(self.edit_actions)
        self.menu_window = tk.Toplevel(self.root)
        self.menu_window.title("Context Badge Menu")
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

        # A normal (non-tool) window that can sit on the taskbar while the
        # overlay is hidden. The badge itself stays TOOLWINDOW so it does not
        # appear there during ordinary use.
        self.taskbar_window = tk.Toplevel(self.root)
        self.taskbar_window.title("Context Badge")
        self.taskbar_window.geometry("240x64+-32000+-32000")
        self.taskbar_window.resizable(False, False)
        self.taskbar_window.protocol("WM_DELETE_WINDOW", self._quit)
        self.taskbar_window.bind("<Map>", self._on_taskbar_map)
        self.taskbar_window.bind("<FocusIn>", self._on_taskbar_map)
        self.taskbar_window.withdraw()

        self.list_store = ListStore(lists_path())
        self.list_bar = ListBar(
            self.root,
            self.list_store,
            expanded=self.list_bar_expanded,
            on_expand_changed=self._on_list_expand,
            on_geometry_changed=self._on_list_geometry,
        )

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
        taskbar_tk_hwnd = self.taskbar_window.winfo_id()
        self.taskbar_hwnd = user32.GetParent(taskbar_tk_hwnd) or taskbar_tk_hwnd
        self._prepare_taskbar_proxy()
        self.last_foreground = 0
        self.last_identity: tuple[str, str] | None = None
        self.current_app_name = "CONTEXT BADGE"
        self.current_title = "Starting…"
        self.move_mode = False
        self.resize_mode = False
        self.menu_open = False
        self._press_job: str | None = None
        self._press_origin: tuple[int, int] | None = None
        self._press_tab: int | None = None
        self._edit_dragging = False
        self.drag_offset = (0, 0)
        self.resize_origin = (0, 0, self.badge_width, self.badge_height)
        self.saved_position = self._load_position()
        self._attach_owned_overlays()
        self._set_click_through(True)
        self._make_edit_button_interactive()
        self._make_menu_interactive()
        self._apply_theme()
        self._apply_layout_metrics()
        self.canvas.bind("<ButtonPress-1>", self._start_drag)
        self.canvas.bind("<B1-Motion>", self._drag)
        self.canvas.bind("<ButtonRelease-1>", self._finish_drag)
        user32.ShowWindow(self.overlay_hwnd, SW_SHOWNOACTIVATE)
        user32.ShowWindow(self.edit_hwnd, SW_SHOWNOACTIVATE)
        self.menu_window.withdraw()
        if self.saved_position is not None:
            self._set_position(*self.saved_position)
        self.dwell = DwellTracker(
            DwellStore(dwell_log_path(), dwell_active_path()),
            noise_seconds=self.dwell_noise_seconds,
            checkpoint_seconds=self.dwell_checkpoint_seconds,
        )
        atexit.register(self.dwell.close)
        self.analysis = AnalysisWindow(self.root, self._dwell_records)
        self.analysis.window.update_idletasks()
        analysis_tk = self.analysis.window.winfo_id()
        self.analysis_hwnd = user32.GetParent(analysis_tk) or analysis_tk
        self.root.after(0, self.refresh)

    def _ensure_dwell_config(self) -> None:
        noise = bounded_int(
            self.config.get("dwell_noise_seconds"),
            DEFAULT_NOISE_SECONDS,
            MIN_NOISE_SECONDS,
            MAX_NOISE_SECONDS,
        )
        checkpoint = bounded_int(
            self.config.get("dwell_checkpoint_seconds"),
            DEFAULT_CHECKPOINT_SECONDS,
            MIN_CHECKPOINT_SECONDS,
            MAX_CHECKPOINT_SECONDS,
        )
        changed = False
        if self.config.get("dwell_noise_seconds") != noise:
            self.config["dwell_noise_seconds"] = noise
            changed = True
        if self.config.get("dwell_checkpoint_seconds") != checkpoint:
            self.config["dwell_checkpoint_seconds"] = checkpoint
            changed = True
        self.dwell_noise_seconds = noise
        self.dwell_checkpoint_seconds = checkpoint
        if changed:
            self._save_config()

    def _ensure_list_bar_config(self) -> None:
        expanded = bool(self.config.get("list_bar_expanded", False))
        if self.config.get("list_bar_expanded") != expanded:
            self.config["list_bar_expanded"] = expanded
            self._save_config()
        self.list_bar_expanded = expanded

    def _on_list_expand(self, expanded: bool) -> None:
        self.list_bar_expanded = expanded
        self.config["list_bar_expanded"] = expanded
        self._save_config()
        self._draw_control_strip()

    def _on_list_geometry(self) -> None:
        if hasattr(self, "overlay_hwnd"):
            self._set_position(self.root.winfo_x(), self.root.winfo_y())

    def _load_config(self) -> dict[str, object]:
        try:
            data = json.loads(config_path().read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            return {}

    def _load_position(self) -> tuple[int, int] | None:
        try:
            return int(self.config["x"]), int(self.config["y"])
        except (ValueError, KeyError, TypeError):
            return None

    def _save_config(self) -> None:
        path = config_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.config, indent=2), encoding="utf-8")

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
        if hasattr(self, "edit_hwnd") and not self.minimized:
            self._raise_edit_control()

    def _attach_owned_overlays(self) -> None:
        # Tk does not preserve a native Win32 owner for overrideredirect
        # Toplevel windows. Explicit ownership is the durable Z-order rule we
        # need: owned edit/menu overlays are always drawn above the badge.
        set_window_owner(self.edit_hwnd, GWLP_HWNDPARENT, self.overlay_hwnd)
        set_window_owner(self.menu_hwnd, GWLP_HWNDPARENT, self.overlay_hwnd)
        if hasattr(self, "list_bar"):
            set_window_owner(self.list_bar.hwnd, GWLP_HWNDPARENT, self.overlay_hwnd)

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
        if self.minimized:
            return
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
        if hasattr(self, "list_bar"):
            self.list_bar.raise_bar()

    def _make_menu_interactive(self) -> None:
        style = user32.GetWindowLongW(self.menu_hwnd, GWL_EXSTYLE)
        style |= WS_EX_LAYERED | WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE
        style &= ~WS_EX_TRANSPARENT
        user32.SetWindowLongW(self.menu_hwnd, GWL_EXSTYLE, style)

    def _tab_index_at(self, x: int) -> int:
        return min(self.TAB_COUNT - 1, max(0, x // self.TAB_WIDTH))

    def _cancel_press_job(self) -> None:
        if self._press_job is not None:
            try:
                self.root.after_cancel(self._press_job)
            except tk.TclError:
                pass
            self._press_job = None

    def _handle_control_press(self, event: tk.Event) -> None:
        if self.resize_mode or self.move_mode:
            self._end_interaction()
            self._press_tab = None
            self._press_origin = None
            return
        index = self._tab_index_at(event.x)
        self._press_tab = index
        self._press_origin = (event.x_root, event.y_root)
        self._edit_dragging = False
        if index == 0:
            self._cancel_press_job()
            self._press_job = self.root.after(
                self.LONG_PRESS_MS, self._start_edit_drag
            )
            return
        self._press_tab = None
        self._press_origin = None
        if index == 1:
            self._toggle_list_bar()
        elif index == 2:
            self._minimize_to_taskbar()
        else:
            self._quit()

    def _handle_control_drag(self, event: tk.Event) -> None:
        if self._edit_dragging:
            self._move_to_pointer(event.x_root, event.y_root)
            return
        if self._press_tab != 0 or self._press_origin is None:
            return
        dx = event.x_root - self._press_origin[0]
        dy = event.y_root - self._press_origin[1]
        if dx * dx + dy * dy >= self.DRAG_THRESHOLD_PX ** 2:
            self._start_edit_drag()
            self._move_to_pointer(event.x_root, event.y_root)

    def _handle_control_release(self, _event: tk.Event) -> None:
        self._cancel_press_job()
        if self._edit_dragging:
            self._finish_edit_drag()
            return
        if self._press_tab == 0:
            self._press_tab = None
            self._press_origin = None
            self._toggle_edit_control()
            return
        self._press_tab = None
        self._press_origin = None

    def _start_edit_drag(self) -> None:
        self._cancel_press_job()
        if self._press_origin is None or self._edit_dragging:
            return
        self._set_menu_open(False)
        self._edit_dragging = True
        self.drag_offset = (
            self._press_origin[0] - self.root.winfo_x(),
            self._press_origin[1] - self.root.winfo_y(),
        )
        try:
            self.edit_canvas.grab_set()
        except tk.TclError:
            pass
        self._set_click_through(False)
        self.edit_canvas.configure(cursor="fleur")
        self._draw_control_strip()

    def _move_to_pointer(self, x_root: int, y_root: int) -> None:
        x = x_root - self.drag_offset[0]
        y = y_root - self.drag_offset[1]
        self.saved_position = (x, y)
        self._set_position(x, y)

    def _finish_edit_drag(self) -> None:
        self._edit_dragging = False
        self._press_tab = None
        self._press_origin = None
        try:
            self.edit_canvas.grab_release()
        except tk.TclError:
            pass
        self.edit_canvas.configure(cursor="hand2")
        self._set_click_through(True)
        self._save_position()
        self._draw_control_strip()

    def _on_control_motion(self, event: tk.Event) -> None:
        if self._edit_dragging or self._press_tab is not None:
            return
        index = self._tab_index_at(event.x)
        if index != self.hovered_tab:
            self.hovered_tab = index
            self._draw_control_strip()

    def _on_control_leave(self, _event: tk.Event) -> None:
        if self._edit_dragging or self._press_job is not None:
            return
        if self.hovered_tab is not None:
            self.hovered_tab = None
            self._draw_control_strip()

    def _toggle_edit_control(self) -> None:
        if self.resize_mode:
            self._end_interaction()
            return
        if not self.menu_open:
            self.menu_page = "main"
            self._render_menu()
        self._set_menu_open(not self.menu_open)

    def _toggle_list_bar(self) -> None:
        if self.resize_mode:
            self._end_interaction()
        self.list_bar.set_expanded(not self.list_bar.expanded)
        self._draw_control_strip()

    def _prepare_taskbar_proxy(self) -> None:
        style = user32.GetWindowLongW(self.taskbar_hwnd, GWL_EXSTYLE)
        style |= WS_EX_APPWINDOW
        style &= ~(WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE)
        user32.SetWindowLongW(self.taskbar_hwnd, GWL_EXSTYLE, style)
        set_window_owner(self.taskbar_hwnd, GWLP_HWNDPARENT, 0)
        user32.SetWindowPos(
            self.taskbar_hwnd,
            0,
            0,
            0,
            0,
            0,
            SWP_NOSIZE | SWP_NOMOVE | SWP_NOACTIVATE | SWP_FRAMECHANGED,
        )

    def _minimize_to_taskbar(self) -> None:
        if self.minimized:
            return
        if self.resize_mode:
            self._end_interaction()
        if self._edit_dragging:
            self._finish_edit_drag()
        self._set_menu_open(False)
        self.minimized = True
        self._suppress_taskbar_map = True
        user32.ShowWindow(self.overlay_hwnd, SW_HIDE)
        user32.ShowWindow(self.edit_hwnd, SW_HIDE)
        user32.ShowWindow(self.menu_hwnd, SW_HIDE)
        self.list_bar.hide()
        self._prepare_taskbar_proxy()
        self.taskbar_window.deiconify()
        self.taskbar_window.iconify()
        self.taskbar_window.after(150, self._release_taskbar_map)

    def _release_taskbar_map(self) -> None:
        self._suppress_taskbar_map = False

    def _on_taskbar_map(self, event: tk.Event) -> None:
        if event.widget is not self.taskbar_window:
            return
        if self._suppress_taskbar_map or not self.minimized:
            return
        try:
            state = str(self.taskbar_window.state())
        except tk.TclError:
            return
        if state == "normal":
            self._restore_from_taskbar()

    def _restore_from_taskbar(self) -> None:
        if not self.minimized:
            return
        self.minimized = False
        self._suppress_taskbar_map = True
        self.taskbar_window.withdraw()
        self.taskbar_window.after(150, self._release_taskbar_map)
        user32.ShowWindow(self.overlay_hwnd, SW_SHOWNOACTIVATE)
        user32.ShowWindow(self.edit_hwnd, SW_SHOWNOACTIVATE)
        self._set_click_through(True)
        self._make_edit_button_interactive()
        self._attach_owned_overlays()
        position = self.saved_position
        if position is None:
            position = (self.root.winfo_x(), self.root.winfo_y())
        self._set_position(*position)
        self.list_bar.show()
        self._apply_theme()

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

    def _open_analysis(self) -> None:
        self._set_menu_open(False)
        x = self.root.winfo_x()
        y = self.root.winfo_y() + self.badge_height + 8
        self.analysis.show(x, y)
        self.analysis.window.update_idletasks()
        analysis_tk = self.analysis.window.winfo_id()
        self.analysis_hwnd = user32.GetParent(analysis_tk) or analysis_tk
        self._show_analysis_prompt()

    def _dwell_records(self) -> list[dict]:
        records = list(self.dwell.store.load_history())
        snapshot = self.dwell.snapshot()
        if snapshot is not None:
            records.append(snapshot)
        else:
            active = self.dwell.store.load_active()
            if active is not None:
                records.append(active)
        return records

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
            and not self.resize_mode
        )
        body_colour = TRANSPARENT_KEY if transparent_now else self.background_color
        self.root.attributes(
            "-transparentcolor", TRANSPARENT_KEY if transparent_now else ""
        )
        self.root.configure(bg=body_colour)
        self.canvas.configure(
            bg=body_colour,
            highlightthickness=0 if transparent_now else 1,
            highlightbackground=self.border_color,
        )
        self.canvas.itemconfigure(self.app_text, fill=self.secondary_text_color)
        self.canvas.itemconfigure(self.title_text, fill=self.text_color)
        # The control strip stays opaque so Menu / List / Hide / Close remain findable.
        self.edit_window.attributes("-transparentcolor", "")
        self.edit_window.configure(bg=self.background_color)
        self.edit_canvas.configure(bg=self.background_color)
        self._update_edit_icon()

    def _quit(self) -> None:
        self._cancel_press_job()
        self.dwell.close("shutdown")
        if self._edit_dragging or self.resize_mode:
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
        self._draw_control_strip()
        self._raise_edit_control()

    def _draw_control_strip(self) -> None:
        canvas = self.edit_canvas
        canvas.delete("all")
        height = self.badge_height
        editing = self.resize_mode
        moving = self._edit_dragging
        list_open = bool(getattr(self, "list_bar", None) and self.list_bar.expanded)
        labels = (
            "Menu",
            "List",
            "Hide",
            "Close",
        )
        icons = (
            "✓" if editing else ("↔" if moving else ("×" if self.menu_open else "☰")),
            "▾" if list_open else "▸",
            "–",
            "×",
        )
        icon_colours = (
            "#8fc0ff" if (editing or moving or self.menu_open) else self.text_color,
            "#8fc0ff" if list_open else self.text_color,
            self.text_color,
            "#ff8f8f",
        )
        for index in range(self.TAB_COUNT):
            x0 = index * self.TAB_WIDTH
            x1 = x0 + self.TAB_WIDTH
            fill = self.background_color
            if self.hovered_tab == index or (
                index == 0 and (editing or moving or self.menu_open)
            ) or (index == 1 and list_open):
                fill = self.hover_color
            canvas.create_rectangle(
                x0,
                0,
                x1,
                height,
                fill=fill,
                outline=fill,
            )
            if index:
                canvas.create_line(
                    x0,
                    self.layout.divider_margin,
                    x0,
                    height - self.layout.divider_margin,
                    fill=self.border_color,
                )
            cx = x0 + self.TAB_WIDTH // 2
            has_label = height >= 56
            icon_y = height // 2 - 8 if has_label else height // 2
            canvas.create_text(
                cx,
                icon_y,
                text=icons[index],
                fill=icon_colours[index],
                font=self.edit_icon_font,
            )
            if has_label:
                canvas.create_text(
                    cx,
                    icon_y + 16,
                    text=labels[index],
                    fill=(
                        icon_colours[index]
                        if index == 3
                        else self.secondary_text_color
                    ),
                    font=self.tab_label_font,
                )
        canvas.create_rectangle(
            0,
            0,
            self.EDIT_WIDTH - 1,
            height - 1,
            fill="",
            outline=self.border_color,
        )

    def _update_app_label(self) -> None:
        if self.resize_mode:
            prefix = "RESIZE MODE · "
        else:
            prefix = ""
        self._render_text(prefix + self.current_app_name, self.current_title)

    def _apply_layout_metrics(self) -> None:
        self.layout = badge_metrics(self.badge_width, self.badge_height)
        self.app_font.configure(size=self.layout.app_font_size)
        self.title_font.configure(size=self.layout.title_font_size)
        self.handle_font.configure(size=self.layout.handle_font_size)
        self.edit_icon_font.configure(size=self.layout.edit_icon_font_size)
        self.tab_label_font.configure(
            size=max(7, min(9, self.layout.app_font_size - 2))
        )
        self.canvas.coords(
            self.app_text, self.layout.padding_x, self.layout.app_y
        )
        self.canvas.coords(
            self.title_text, self.layout.padding_x, self.layout.title_y
        )
        self.canvas.coords(
            self.resize_handle,
            self.badge_width - self.EDIT_WIDTH - self.layout.handle_inset_x,
            self.badge_height - self.layout.handle_inset_y,
        )
        self._draw_control_strip()

    def _render_text(self, app_label: str, title: str) -> None:
        available_width = max(
            80,
            self.badge_width
            - self.EDIT_WIDTH
            - self.layout.padding_x
            - self.layout.text_right_gap,
        )
        app_display = fit_text(app_label, self.app_font, available_width, 1)
        line_height = max(1, self.title_font.metrics("linespace"))
        available_height = max(
            line_height,
            self.badge_height - self.layout.title_y - self.layout.text_bottom_gap,
        )
        max_lines = max(1, available_height // line_height)
        title_display = fit_text(title, self.title_font, available_width, max_lines)
        self.canvas.itemconfigure(self.app_text, text=app_display)
        self.canvas.itemconfigure(
            self.title_text, text=title_display, width=available_width
        )

    def _set_badge_size(self, width: int, height: int) -> None:
        self.badge_width = int(width)
        self.badge_height = int(height)
        self.canvas.configure(width=self.badge_width, height=self.badge_height)
        self.edit_canvas.configure(width=self.EDIT_WIDTH, height=self.badge_height)
        self._apply_layout_metrics()
        self._set_position(self.root.winfo_x(), self.root.winfo_y())
        self._update_app_label()

    def _start_drag(self, event: tk.Event) -> None:
        if self.resize_mode:
            self.resize_origin = (
                event.x_root,
                event.y_root,
                self.badge_width,
                self.badge_height,
            )

    def _drag(self, event: tk.Event) -> None:
        if self._edit_dragging:
            self._move_to_pointer(event.x_root, event.y_root)
            return
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

    def _finish_drag(self, _event: tk.Event) -> None:
        if self._edit_dragging:
            self._finish_edit_drag()
            return
        if self.resize_mode:
            self._save_position()

    def _set_position(self, x: int, y: int) -> None:
        if self.minimized:
            return
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
        if hasattr(self, "list_bar"):
            list_y = y + self.badge_height + GAP_FROM_BADGE
            self.list_bar.set_position(x, list_y, self.badge_width)
            menu_y = list_y + self.list_bar.height() + 6
        else:
            menu_y = y + self.badge_height + 6
        menu_x = x + self.badge_width - self.menu_width
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
        if self.minimized:
            return
        if self.saved_position is not None:
            self._set_position(*self.saved_position)
            return
        work = monitor_work_area(foreground)
        x = work.left + ((work.right - work.left) - self.badge_width) // 2
        y = work.top + self.TOP_MARGIN
        self._set_position(x, y)

    def _analysis_is_foreground(self, hwnd: int) -> bool:
        if not hwnd or not getattr(self, "analysis", None):
            return False
        try:
            inner = int(self.analysis.window.winfo_id())
        except tk.TclError:
            return False
        outer = user32.GetParent(inner) or inner
        self.analysis_hwnd = outer
        focused = root_hwnd(hwnd)
        return focused in (root_hwnd(inner), root_hwnd(outer), outer, inner)

    def _show_analysis_prompt(self) -> None:
        identity = ("context_badge", "Time analysis")
        title = self.analysis.prompt_text()
        if identity != self.last_identity or self.current_title != title:
            self.current_app_name = "TIME ANALYSIS"
            self.current_title = title
            self._update_app_label()
            self.last_identity = identity

    def refresh(self) -> None:
        foreground = user32.GetForegroundWindow()
        if foreground and self._analysis_is_foreground(foreground):
            self._show_analysis_prompt()
            self.dwell.observe(
                DwellObservation(
                    executable="context_badge",
                    app="Context Badge",
                    title="Time analysis",
                )
            )
            if self.last_foreground:
                self._move_to_active_monitor(self.last_foreground)
            self.list_bar.set_key("context_badge", "Time analysis")
            self.root.after(self.POLL_MS, self.refresh)
            return
        if foreground and foreground not in (
            self.overlay_hwnd,
            self.edit_hwnd,
            self.menu_hwnd,
            self.taskbar_hwnd,
            self.list_bar.hwnd,
        ) and root_hwnd(foreground) != self.list_bar.hwnd:
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
            self.dwell.observe(
                DwellObservation(
                    executable=executable,
                    app=friendly_app_name(executable),
                    title=title,
                )
            )
            self.list_bar.set_key(executable, surface_label(executable, title))
            self._move_to_active_monitor(foreground)

        self.root.after(self.POLL_MS, self.refresh)

    def run(self) -> None:
        try:
            self.root.mainloop()
        except KeyboardInterrupt:
            # Ctrl+C is the Step 1 exit mechanism. Avoid printing a traceback.
            self.dwell.close("shutdown")
            self.root.destroy()


if __name__ == "__main__":
    ContextBadge().run()
