"""Context Badge: a persistent, non-interactive Windows desktop overlay.

Step 1 deliberately has no third-party dependencies.  It observes the current
foreground top-level window and displays its application and title.
"""

from __future__ import annotations

import atexit
import json
import time
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
from .surface import BROWSER_SUFFIXES, resolve_context
from .text_layout import fit_text
from .theme import (
    COLOUR_PALETTE,
    DEFAULT_BACKGROUND,
    DEFAULT_LIST_BACKGROUND,
    DEFAULT_TEXT,
    TRANSPARENT,
    TRANSPARENT_KEY,
    blend_hex,
    bounded_int,
    is_transparent,
    paint_color,
)
from .uia import UiaSnapshot, inspect_window
from .win32 import (
    GWL_EXSTYLE,
    GWLP_HWNDPARENT,
    HWND_TOPMOST,
    LWA_ALPHA,
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
    UNLOCK_WIDTH = 72
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
        self.border_color = self.config.get("border_color")
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
        self._ensure_lock_config()
        self._ensure_colour_config()
        blend_base = self._blend_base()
        self.secondary_text_color = blend_hex(blend_base, self.text_color, 0.68)
        if not (
            isinstance(self.border_color, str)
            and self.border_color.startswith("#")
            and len(self.border_color) == 7
        ):
            self.border_color = blend_hex(blend_base, self.text_color, 0.22)
        self.hover_color = blend_hex(blend_base, self.text_color, 0.12)

        start_bg = paint_color(self.background_color)
        self.root = tk.Tk()
        self.root.title("Context Badge")
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        self.root.configure(bg=start_bg)
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
            bg=start_bg,
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
        self.edit_window.configure(bg=start_bg)
        self.edit_canvas = tk.Canvas(
            self.edit_window,
            width=self.EDIT_WIDTH,
            height=self.badge_height,
            bg=start_bg,
            highlightthickness=0,
            cursor="hand2",
        )
        self.edit_canvas.pack()
        self.edit_canvas.bind("<ButtonPress-1>", self._handle_control_press)
        self.edit_canvas.bind("<B1-Motion>", self._handle_control_drag)
        self.edit_canvas.bind("<ButtonRelease-1>", self._handle_control_release)
        self.edit_canvas.bind("<Motion>", self._on_control_motion)
        self.edit_canvas.bind("<Leave>", self._on_control_leave)

        # Colour-keyed pixels do not receive hits. When the badge is unlocked
        # and visually transparent, this nearly-invisible layered window sits
        # over the body only, so Menu / List / Hide / Close stay clickable.
        self.hit_window = tk.Toplevel(self.root)
        self.hit_window.title("Context Badge hit target")
        self.hit_window.overrideredirect(True)
        self.hit_window.attributes("-topmost", True)
        self.hit_window.configure(bg="#000000")
        self.hit_canvas = tk.Canvas(
            self.hit_window,
            width=max(1, self.badge_width - self.EDIT_WIDTH),
            height=self.badge_height,
            bg="#000000",
            highlightthickness=0,
            cursor="fleur",
        )
        self.hit_canvas.pack()
        self.hit_canvas.bind("<ButtonPress-1>", self._start_drag)
        self.hit_canvas.bind("<B1-Motion>", self._drag)
        self.hit_canvas.bind("<ButtonRelease-1>", self._finish_drag)
        self.hit_window.withdraw()

        # The first level stays compact. All appearance controls live under the
        # Colours second-level page. Close lives on the control strip. Drag the
        # badge body (or long-press Menu) to move unless Fix is on.
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
        hit_tk_hwnd = self.hit_window.winfo_id()
        self.hit_hwnd = user32.GetParent(hit_tk_hwnd) or hit_tk_hwnd
        menu_tk_hwnd = self.menu_window.winfo_id()
        self.menu_hwnd = user32.GetParent(menu_tk_hwnd) or menu_tk_hwnd
        taskbar_tk_hwnd = self.taskbar_window.winfo_id()
        self.taskbar_hwnd = user32.GetParent(taskbar_tk_hwnd) or taskbar_tk_hwnd
        self._prepare_taskbar_proxy()
        self.last_foreground = 0
        self.last_identity: tuple[object, ...] | None = None
        self._uia_hwnd = 0
        self._uia_raw_title = ""
        self._uia_at = 0.0
        self._uia_snap = None
        self.current_app_name = "CONTEXT BADGE"
        self.current_title = "Starting…"
        self.move_mode = False
        self.resize_mode = False
        self.menu_open = False
        self._press_job: str | None = None
        self._press_origin: tuple[int, int] | None = None
        self._press_tab: int | None = None
        self._edit_dragging = False
        self._body_dragging = False
        self._body_press_origin: tuple[int, int] | None = None
        self.drag_offset = (0, 0)
        self.resize_origin = (0, 0, self.badge_width, self.badge_height)
        self.saved_position = self._load_position()
        self._attach_owned_overlays()
        self._make_edit_button_interactive()
        self._prepare_hit_catcher()
        self._make_menu_interactive()
        self._apply_theme()
        self._apply_pointer_mode()
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

    def _ensure_lock_config(self) -> None:
        locked = bool(self.config.get("position_locked", False))
        if self.config.get("position_locked") != locked:
            self.config["position_locked"] = locked
            self._save_config()
        self.position_locked = locked

    def _ensure_colour_config(self) -> None:
        changed = False
        if self.config.get("background_transparent"):
            self.background_color = TRANSPARENT
            changed = True
        if is_transparent(self.background_color):
            self.background_color = TRANSPARENT
        elif not (
            isinstance(self.background_color, str)
            and self.background_color.startswith("#")
            and len(self.background_color) == 7
        ):
            self.background_color = DEFAULT_BACKGROUND
        if self.config.get("background_color") != self.background_color:
            self.config["background_color"] = self.background_color
            changed = True
        if "background_transparent" in self.config:
            del self.config["background_transparent"]
            changed = True
        list_bg = self.config.get("list_background_color", DEFAULT_LIST_BACKGROUND)
        if is_transparent(list_bg):
            list_bg = TRANSPARENT
        elif not (
            isinstance(list_bg, str)
            and list_bg.startswith("#")
            and len(list_bg) == 7
        ):
            list_bg = DEFAULT_LIST_BACKGROUND
        self.list_background_color = list_bg
        if self.config.get("list_background_color") != list_bg:
            self.config["list_background_color"] = list_bg
            changed = True
        if changed:
            self._save_config()

    def _blend_base(self) -> str:
        if is_transparent(self.background_color):
            return DEFAULT_BACKGROUND
        return str(self.background_color)

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

    def _apply_pointer_mode(self) -> None:
        interactive = (
            self.resize_mode
            or self._edit_dragging
            or self._body_dragging
            or not self.position_locked
        )
        self._set_click_through(not interactive)
        if self.resize_mode:
            self.canvas.configure(cursor="sizing")
            if hasattr(self, "hit_canvas"):
                self.hit_canvas.configure(cursor="sizing")
        elif not self.position_locked:
            self.canvas.configure(cursor="fleur")
            if hasattr(self, "hit_canvas"):
                self.hit_canvas.configure(cursor="fleur")
        else:
            self.canvas.configure(cursor="")
        if not self.minimized:
            self._make_edit_button_interactive()
        self._sync_hit_catcher()

    def _strip_width(self) -> int:
        if getattr(self, "position_locked", False):
            return self.UNLOCK_WIDTH
        return self.EDIT_WIDTH

    def _hit_body_width(self) -> int:
        return max(1, self.badge_width - self._strip_width())

    def _attach_owned_overlays(self) -> None:
        # Tk does not preserve a native Win32 owner for overrideredirect
        # Toplevel windows. Explicit ownership is the durable Z-order rule we
        # need: owned edit/menu overlays are always drawn above the badge.
        set_window_owner(self.edit_hwnd, GWLP_HWNDPARENT, self.overlay_hwnd)
        if hasattr(self, "hit_hwnd"):
            set_window_owner(self.hit_hwnd, GWLP_HWNDPARENT, self.overlay_hwnd)
        set_window_owner(self.menu_hwnd, GWLP_HWNDPARENT, self.overlay_hwnd)
        if hasattr(self, "list_bar"):
            set_window_owner(self.list_bar.hwnd, GWLP_HWNDPARENT, self.overlay_hwnd)

    def _prepare_hit_catcher(self) -> None:
        style = user32.GetWindowLongW(self.hit_hwnd, GWL_EXSTYLE)
        style |= WS_EX_LAYERED | WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE
        style &= ~WS_EX_TRANSPARENT
        user32.SetWindowLongW(self.hit_hwnd, GWL_EXSTYLE, style)
        user32.SetLayeredWindowAttributes(self.hit_hwnd, 0, 1, LWA_ALPHA)
        user32.SetWindowPos(
            self.hit_hwnd,
            HWND_TOPMOST,
            0,
            0,
            0,
            0,
            SWP_NOSIZE | SWP_NOMOVE | SWP_NOACTIVATE | SWP_FRAMECHANGED,
        )

    def _hit_catcher_needed(self) -> bool:
        return (
            not self.minimized
            and not self.position_locked
            and is_transparent(self.background_color)
            and not self.resize_mode
        )

    def _sync_hit_catcher(self) -> None:
        if not hasattr(self, "hit_hwnd"):
            return
        if self._hit_catcher_needed():
            width = self._hit_body_width()
            self.hit_window.geometry(
                f"{width}x{self.badge_height}"
                f"+{self.root.winfo_x()}+{self.root.winfo_y()}"
            )
            self.hit_canvas.configure(width=width, height=self.badge_height)
            self.hit_window.deiconify()
            self._prepare_hit_catcher()
            user32.ShowWindow(self.hit_hwnd, SW_SHOWNOACTIVATE)
            if not self.minimized:
                self._raise_edit_control()
        else:
            user32.ShowWindow(self.hit_hwnd, SW_HIDE)
            self.hit_window.withdraw()

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
        if self._hit_catcher_needed():
            user32.SetWindowPos(
                self.hit_hwnd,
                HWND_TOPMOST,
                0,
                0,
                0,
                0,
                SWP_NOSIZE | SWP_NOMOVE | SWP_NOACTIVATE | SWP_SHOWWINDOW,
            )
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
        if self.position_locked:
            return 0
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
        if self.position_locked:
            self._press_tab = 0
            self._press_origin = (event.x_root, event.y_root)
            self._edit_dragging = False
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
        if self.position_locked:
            return
        if self._edit_dragging:
            self._move_to_pointer(event.x_root, event.y_root)
            return
        if self._press_tab != 0 or self._press_origin is None:
            return
        dx = event.x_root - self._press_origin[0]
        dy = event.y_root - self._press_origin[1]
        if dx * dx + dy * dy >= self.DRAG_THRESHOLD_PX ** 2:
            self._start_edit_drag()
            if self._edit_dragging:
                self._move_to_pointer(event.x_root, event.y_root)

    def _handle_control_release(self, _event: tk.Event) -> None:
        self._cancel_press_job()
        if self._edit_dragging:
            self._finish_edit_drag()
            return
        if self.position_locked and self._press_tab == 0:
            self._press_tab = None
            self._press_origin = None
            self._toggle_lock()
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
        if self.position_locked or self._press_origin is None or self._edit_dragging:
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
        self._apply_pointer_mode()
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
        if self.position_locked:
            return
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
        if hasattr(self, "hit_hwnd"):
            user32.ShowWindow(self.hit_hwnd, SW_HIDE)
            self.hit_window.withdraw()
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
        self._apply_pointer_mode()
        self._make_edit_button_interactive()
        self._attach_owned_overlays()
        position = self.saved_position
        if position is None:
            position = (self.root.winfo_x(), self.root.winfo_y())
        self._set_position(*position)
        self.list_bar.show()
        self._apply_theme()

    def _main_menu_rows(self) -> list[tuple[str, object, str]]:
        return [
            ("\u25f2  Resize badge", self._begin_resize, "#f3f5f7"),
            ("\u2610  Fix", self._toggle_lock, "#f3f5f7"),
            ("\u25c9  Colours  \u203a", self._open_colours, "#f3f5f7"),
            ("\u25f7  Time analysis", self._open_analysis, "#f3f5f7"),
        ]

    def _toggle_lock(self) -> None:
        self.position_locked = not self.position_locked
        self.config["position_locked"] = self.position_locked
        self._save_config()
        self.menu_page = "main"
        self._set_menu_open(False)
        self._apply_theme()
        self._apply_pointer_mode()
        self._apply_layout_metrics()
        self._update_app_label()
        if hasattr(self, "overlay_hwnd"):
            self._set_position(self.root.winfo_x(), self.root.winfo_y())

    def _render_menu(self) -> None:
        self.menu_canvas.delete("all")
        if self.menu_page == "main":
            self.edit_actions = self._main_menu_rows()
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
        self.menu_height = self.COLOUR_HEADER_HEIGHT + self.COLOUR_ROW_HEIGHT * 4
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
            ("Background", self.background_color, True),
            ("List", self.list_background_color, True),
            ("Text", self.text_color, False),
            ("Border", self.border_color, False),
        )
        swatch_x = 106
        swatch_size = 17
        swatch_gap = 5
        for row, (label, selected, allow_clear) in enumerate(properties):
            row_top = self.COLOUR_HEADER_HEIGHT + row * self.COLOUR_ROW_HEIGHT
            self.menu_canvas.create_text(
                14,
                row_top + self.COLOUR_ROW_HEIGHT // 2,
                anchor="w",
                text=label,
                fill="#f3f5f7",
                font=("Segoe UI", 10),
            )
            if allow_clear:
                clear_on = is_transparent(selected)
                self.menu_canvas.create_rectangle(
                    80,
                    row_top + 18,
                    97,
                    row_top + 35,
                    fill="#20232a",
                    outline="#ffffff" if clear_on else "#596170",
                    width=2 if clear_on else 1,
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
                chosen = (
                    not is_transparent(selected)
                    and colour.lower() == str(selected).lower()
                )
                outline = "#ffffff" if chosen else "#596170"
                width = 2 if chosen else 1
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
        keys = (
            "background_color",
            "list_background_color",
            "text_color",
            "border_color",
        )
        if not 0 <= row < len(keys):
            return
        if row < 2 and 80 <= event.x <= 97 and 18 <= local_y <= 35:
            self._set_colour(keys[row], TRANSPARENT)
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
            self._set_colour(keys[row], COLOUR_PALETTE[swatch])

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
        if key not in {
            "background_color",
            "list_background_color",
            "text_color",
            "border_color",
        }:
            return
        setattr(self, key, selected)
        self.config[key] = selected
        self._apply_theme()
        self._save_config()
        self._render_menu()

    def _apply_theme(self) -> None:
        blend_base = self._blend_base()
        self.secondary_text_color = blend_hex(blend_base, self.text_color, 0.68)
        self.hover_color = blend_hex(blend_base, self.text_color, 0.12)
        transparent_now = (
            is_transparent(self.background_color) and not self.resize_mode
        )
        if transparent_now:
            body_colour = TRANSPARENT_KEY
        elif is_transparent(self.background_color):
            body_colour = DEFAULT_BACKGROUND
        else:
            body_colour = str(self.background_color)
        self.root.attributes(
            "-transparentcolor", TRANSPARENT_KEY if transparent_now else ""
        )
        self.root.configure(bg=body_colour)
        hide_border = transparent_now and self.position_locked
        self.canvas.configure(
            bg=body_colour,
            highlightthickness=0 if hide_border else 1,
            highlightbackground=self.border_color,
        )
        self.canvas.itemconfigure(self.app_text, fill=self.secondary_text_color)
        self.canvas.itemconfigure(self.title_text, fill=self.text_color)
        strip_colour = body_colour
        self.edit_window.attributes(
            "-transparentcolor", TRANSPARENT_KEY if transparent_now else ""
        )
        self.edit_window.configure(bg=strip_colour)
        self.edit_canvas.configure(bg=strip_colour)
        self._update_edit_icon()
        self._sync_hit_catcher()
        if hasattr(self, "list_bar"):
            self.list_bar.apply_theme(
                background=self.list_background_color,
                text=self.text_color,
                muted=self.secondary_text_color,
            )

    def _quit(self) -> None:
        self._cancel_press_job()
        self.dwell.close("shutdown")
        if self._edit_dragging or self._body_dragging or self.resize_mode:
            self._save_position()
        self.root.destroy()

    def _end_interaction(self) -> None:
        self._save_position()
        self.move_mode = False
        self.resize_mode = False
        self._apply_theme()
        self._apply_pointer_mode()
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
        moving = self._edit_dragging or self._body_dragging
        list_open = bool(getattr(self, "list_bar", None) and self.list_bar.expanded)
        ghost = is_transparent(self.background_color) and not self.resize_mode
        tab_fill = TRANSPARENT_KEY if ghost else paint_color(self.background_color)
        strip_width = self._strip_width()
        if self.position_locked:
            hovered = self.hovered_tab == 0
            fill = tab_fill
            if not ghost and hovered:
                fill = self.hover_color
            canvas.create_rectangle(
                0, 0, strip_width, height, fill=fill, outline=fill
            )
            colour = "#8fc0ff" if hovered else self.text_color
            has_label = height >= 56
            cx = strip_width // 2
            icon_y = height // 2 - 8 if has_label else height // 2
            canvas.create_text(
                cx,
                icon_y,
                text="\u25cb",
                fill=colour,
                font=self.edit_icon_font,
            )
            if has_label:
                canvas.create_text(
                    cx,
                    icon_y + 16,
                    text="Unlock",
                    fill=colour if hovered else self.secondary_text_color,
                    font=self.tab_label_font,
                )
            if not ghost:
                canvas.create_rectangle(
                    0,
                    0,
                    strip_width - 1,
                    height - 1,
                    fill="",
                    outline=self.border_color,
                )
            return
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
            hovered = self.hovered_tab == index
            active = (index == 0 and (editing or moving or self.menu_open)) or (
                index == 1 and list_open
            )
            fill = tab_fill
            if not ghost and (hovered or active):
                fill = self.hover_color
            canvas.create_rectangle(
                x0,
                0,
                x1,
                height,
                fill=fill,
                outline=fill,
            )
            if index and not ghost:
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
            colour = icon_colours[index]
            if ghost and hovered and not active and index != 3:
                colour = "#8fc0ff"
            canvas.create_text(
                cx,
                icon_y,
                text=icons[index],
                fill=colour,
                font=self.edit_icon_font,
            )
            if has_label:
                if index == 3:
                    label_colour = colour
                elif ghost and hovered:
                    label_colour = colour
                else:
                    label_colour = self.secondary_text_color
                canvas.create_text(
                    cx,
                    icon_y + 16,
                    text=labels[index],
                    fill=label_colour,
                    font=self.tab_label_font,
                )
        if not ghost:
            canvas.create_rectangle(
                0,
                0,
                strip_width - 1,
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
        if hasattr(self, "list_bar"):
            self.list_bar.apply_layout(
                font_size=self.layout.list_font_size,
                count_font_size=self.layout.list_count_font_size,
                header_height=self.layout.list_header_height,
                row_height=self.layout.list_row_height,
                add_height=self.layout.list_add_height,
            )
        self.canvas.coords(
            self.app_text, self.layout.padding_x, self.layout.app_y
        )
        self.canvas.coords(
            self.title_text, self.layout.padding_x, self.layout.title_y
        )
        self.canvas.coords(
            self.resize_handle,
            self.badge_width - self._strip_width() - self.layout.handle_inset_x,
            self.badge_height - self.layout.handle_inset_y,
        )
        self.edit_canvas.configure(
            width=self._strip_width(), height=self.badge_height
        )
        self._draw_control_strip()

    def _render_text(self, app_label: str, title: str) -> None:
        available_width = max(
            80,
            self.badge_width
            - self._strip_width()
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
        self.edit_canvas.configure(
            width=self._strip_width(), height=self.badge_height
        )
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
            return
        if self.position_locked:
            return
        self._body_press_origin = (event.x_root, event.y_root)
        self._body_dragging = False
        self.drag_offset = (
            event.x_root - self.root.winfo_x(),
            event.y_root - self.root.winfo_y(),
        )

    def _drag(self, event: tk.Event) -> None:
        if self._edit_dragging:
            self._move_to_pointer(event.x_root, event.y_root)
            return
        if self.resize_mode:
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
            return
        if self.position_locked or self._body_press_origin is None:
            return
        if not self._body_dragging:
            dx = event.x_root - self._body_press_origin[0]
            dy = event.y_root - self._body_press_origin[1]
            if dx * dx + dy * dy < self.DRAG_THRESHOLD_PX ** 2:
                return
            self._body_dragging = True
            self._set_menu_open(False)
            self.canvas.configure(cursor="fleur")
            self._draw_control_strip()
        self._move_to_pointer(event.x_root, event.y_root)

    def _finish_drag(self, _event: tk.Event) -> None:
        if self._edit_dragging:
            self._finish_edit_drag()
            return
        if self.resize_mode:
            self._save_position()
            return
        if self._body_dragging:
            self._body_dragging = False
            self._body_press_origin = None
            self._save_position()
            self._draw_control_strip()
            return
        self._body_press_origin = None

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
        if hasattr(self, "hit_hwnd"):
            hit_w = self._hit_body_width()
            self.hit_window.geometry(f"{hit_w}x{self.badge_height}+{x}+{y}")
            self.hit_canvas.configure(width=hit_w, height=self.badge_height)
            if self._hit_catcher_needed():
                user32.SetWindowPos(
                    self.hit_hwnd,
                    HWND_TOPMOST,
                    x,
                    y,
                    0,
                    0,
                    SWP_NOSIZE | SWP_NOACTIVATE | SWP_SHOWWINDOW,
                )
        edit_x = x + self.badge_width - self._strip_width()
        edit_y = y
        self.edit_window.geometry(
            f"{self._strip_width()}x{self.badge_height}+{edit_x}+{edit_y}"
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

    def _foreground_snapshot(
        self, hwnd: int, executable: str, title: str
    ) -> UiaSnapshot | None:
        now = time.monotonic()
        lower = executable.lower()
        browser = lower in BROWSER_SUFFIXES
        agents = title.strip().lower() == "cursor agents"
        changed = hwnd != self._uia_hwnd or title != self._uia_raw_title
        stale = agents and now - self._uia_at >= 0.8
        if changed or stale:
            snap = inspect_window(hwnd, browser=browser, agents=agents)
            if snap is not None:
                self._uia_snap = snap
            elif changed:
                self._uia_snap = None
            self._uia_hwnd = hwnd
            self._uia_raw_title = title
            self._uia_at = now
        return self._uia_snap

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
            resolved = resolve_context(
                executable,
                title,
                self._foreground_snapshot(foreground, executable, title),
            )
            identity = (executable, resolved.display, resolved.list_surface)
            if identity != self.last_identity:
                self.current_app_name = friendly_app_name(executable).upper()
                self.current_title = resolved.display
                self._update_app_label()
                self.last_identity = identity
            self.dwell.observe(
                DwellObservation(
                    executable=executable,
                    app=friendly_app_name(executable),
                    title=resolved.display,
                    page=resolved.dwell_surface,
                )
            )
            self.list_bar.set_key(
                executable,
                resolved.list_surface,
                label=resolved.display,
            )
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
