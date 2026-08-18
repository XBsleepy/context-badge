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
from .menu_popup import MenuPopup
from .paths import (
    config_path,
    dwell_active_path,
    dwell_log_path,
    find_pet_folder,
    lists_path,
)
from .pet_overlay import PetOverlay
from .pet_place import (
    BadgeAnchor,
    PetSize,
    keep_sit_offset,
    normalize_placement,
    normalize_scale_percent,
    relative_offset,
)
from .surface import BROWSER_SUFFIXES, resolve_context
from .text_layout import fit_text
from .theme import (
    DEFAULT_BACKGROUND,
    DEFAULT_BORDER,
    DEFAULT_CORNER_RADIUS,
    DEFAULT_LIST_BACKGROUND,
    DEFAULT_TEXT,
    MAX_CORNER_RADIUS,
    MIN_CORNER_RADIUS,
    TRANSPARENT,
    TRANSPARENT_KEY,
    blend_hex,
    bounded_int,
    is_hex_color,
    is_transparent,
    matching_theme_id,
    paint_color,
    theme_by_id,
)
from .bubble import draw_rounded_panel
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
    TOP_MARGIN = 18
    DEFAULT_PET_ID = "qiuli"
    POLL_MS = 200
    LONG_PRESS_MS = 400
    DRAG_THRESHOLD_PX = 8

    def __init__(self) -> None:
        self.config = self._load_config()
        self.background_color = self.config.get(
            "background_color", DEFAULT_BACKGROUND
        )
        self.text_color = self.config.get("text_color", DEFAULT_TEXT)
        self.border_color = self.config.get("border_color", DEFAULT_BORDER)
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
        self._ensure_pet_config()
        self._ensure_lock_config()
        self._ensure_colour_config()
        self._ensure_radius_config()
        blend_base = self._blend_base()
        self.secondary_text_color = blend_hex(blend_base, self.text_color, 0.68)
        if not is_hex_color(self.border_color):
            self.border_color = DEFAULT_BORDER
        self.hover_color = blend_hex(blend_base, self.text_color, 0.12)

        self.root = tk.Tk()
        self.root.title("Context Badge")
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        self.root.attributes("-transparentcolor", TRANSPARENT_KEY)
        self.root.configure(bg=TRANSPARENT_KEY)
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
            bg=TRANSPARENT_KEY,
            highlightthickness=0,
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
        self.edit_window.attributes("-transparentcolor", TRANSPARENT_KEY)
        self.edit_window.configure(bg=TRANSPARENT_KEY)
        self.edit_canvas = tk.Canvas(
            self.edit_window,
            width=self.EDIT_WIDTH,
            height=self.badge_height,
            bg=TRANSPARENT_KEY,
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

        # Appearance controls live in a standalone rounded popup so later
        # pages can be added without crowding the badge.
        self.menu = MenuPopup(
            self.root,
            on_action=self._on_menu_action,
            on_theme=self._apply_colour_theme,
            on_colour=self._set_colour,
            on_radius=self._set_corner_radius,
            on_pet_action=self._on_pet_action,
        )
        self.menu.set_actions(self._menu_actions())
        self.menu_open = False

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
        self.pet = PetOverlay(self.root, on_pointer=self._on_pet_pointer)

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
        self.menu_hwnd = self.menu.hwnd
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
        self.pet_place_mode = False
        self.pet_size_mode = False
        self._pet_press: tuple[int, int] | None = None
        self._pet_dragging = False
        self._pet_size_origin: tuple[int, int, int] | None = None
        self._pet_place_origin: tuple[int, int, tuple[int, int]] | None = None
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
        self._boot_pet()
        self._make_edit_button_interactive()
        self._prepare_hit_catcher()
        self._apply_theme()
        self._apply_pointer_mode()
        self._apply_layout_metrics()
        self.canvas.bind("<ButtonPress-1>", self._start_drag)
        self.canvas.bind("<B1-Motion>", self._drag)
        self.canvas.bind("<ButtonRelease-1>", self._finish_drag)
        user32.ShowWindow(self.overlay_hwnd, SW_SHOWNOACTIVATE)
        user32.ShowWindow(self.edit_hwnd, SW_SHOWNOACTIVATE)
        self.menu.hide()
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
        if not is_hex_color(self.text_color):
            self.text_color = DEFAULT_TEXT
            changed = True
        if self.config.get("text_color") != self.text_color:
            self.config["text_color"] = self.text_color
            changed = True
        if not is_hex_color(self.border_color):
            self.border_color = DEFAULT_BORDER
            changed = True
        if self.config.get("border_color") != self.border_color:
            self.config["border_color"] = self.border_color
            changed = True
        if changed:
            self._save_config()

    def _ensure_radius_config(self) -> None:
        radius = bounded_int(
            self.config.get("corner_radius"),
            DEFAULT_CORNER_RADIUS,
            MIN_CORNER_RADIUS,
            MAX_CORNER_RADIUS,
        )
        if self.config.get("corner_radius") != radius:
            self.config["corner_radius"] = radius
            self._save_config()
        self.corner_radius = radius

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

    def _ensure_pet_config(self) -> None:
        changed = False
        enabled = bool(self.config.get("pet_enabled", True))
        if self.config.get("pet_enabled") != enabled:
            self.config["pet_enabled"] = enabled
            changed = True
        pet_id = str(self.config.get("pet_id") or self.DEFAULT_PET_ID).strip()
        if not pet_id:
            pet_id = self.DEFAULT_PET_ID
        if self.config.get("pet_id") != pet_id:
            self.config["pet_id"] = pet_id
            changed = True
        placement = normalize_placement(self.config.get("pet_placement"))
        if self.config.get("pet_placement") != placement:
            self.config["pet_placement"] = placement
            changed = True
        scale = normalize_scale_percent(self.config.get("pet_scale_percent"))
        if self.config.get("pet_scale_percent") != scale:
            self.config["pet_scale_percent"] = scale
            changed = True
        offset_x = self.config.get("pet_offset_x")
        offset_y = self.config.get("pet_offset_y")
        if offset_x is not None and offset_y is not None:
            try:
                pet_offset_x = int(offset_x)
                pet_offset_y = int(offset_y)
            except (TypeError, ValueError):
                pet_offset_x = None
                pet_offset_y = None
        else:
            pet_offset_x = None
            pet_offset_y = None
        self.pet_enabled = enabled
        self.pet_id = pet_id
        self.pet_placement = placement
        self.pet_scale_percent = scale
        self.pet_offset_x = pet_offset_x
        self.pet_offset_y = pet_offset_y
        if changed:
            self._save_config()

    def _boot_pet(self) -> None:
        if not hasattr(self, "pet"):
            return
        self.pet.set_placement(self.pet_placement)
        folder = find_pet_folder(self.pet_id) if self.pet_enabled else None
        loaded = False
        if folder is not None:
            loaded = self.pet.load(
                folder, scale=self.pet_scale_percent / 100.0
            )
        self.pet.set_enabled(bool(self.pet_enabled and loaded))

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
            or self.pet_place_mode
            or self.pet_size_mode
            or self._edit_dragging
            or self._body_dragging
            or not self.position_locked
        )
        self._set_click_through(not interactive)
        if hasattr(self, "pet"):
            self.pet.set_click_through(
                self.position_locked
                and not self.pet_place_mode
                and not self.pet_size_mode
            )
            if self.pet_size_mode:
                self.pet.set_pointer_mode("size")
            elif self.pet_place_mode:
                self.pet.set_pointer_mode("place")
            else:
                self.pet.set_pointer_mode("move")
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
        set_window_owner(self.menu.hwnd, GWLP_HWNDPARENT, self.overlay_hwnd)
        if hasattr(self, "list_bar"):
            set_window_owner(self.list_bar.hwnd, GWLP_HWNDPARENT, self.overlay_hwnd)
        if hasattr(self, "pet"):
            self.pet.set_owner(self.overlay_hwnd)

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
        if hasattr(self, "pet"):
            self.pet.raise_pet()
        user32.SetWindowPos(
            self.edit_hwnd,
            HWND_TOPMOST,
            0,
            0,
            0,
            0,
            SWP_NOSIZE | SWP_NOMOVE | SWP_NOACTIVATE | SWP_SHOWWINDOW,
        )
        if hasattr(self, "list_bar"):
            self.list_bar.raise_bar()
        if getattr(self, "menu_open", False) and hasattr(self, "menu"):
            self.menu.raise_popup()

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
        if self.resize_mode or self.move_mode or self.pet_place_mode or self.pet_size_mode:
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
        if self.resize_mode or self.pet_place_mode or self.pet_size_mode:
            self._end_interaction()
            return
        self._set_menu_open(not self.menu_open)

    def _toggle_list_bar(self) -> None:
        if self.resize_mode or self.pet_place_mode or self.pet_size_mode:
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
        if self.resize_mode or self.pet_place_mode or self.pet_size_mode:
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
        user32.ShowWindow(self.menu.hwnd, SW_HIDE)
        self.menu.hide()
        self.list_bar.hide()
        if hasattr(self, "pet"):
            self.pet.hide()
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

    def _menu_actions(self) -> list[tuple[str, str]]:
        return [
            ("resize", "Resize badge"),
            ("fix", "Fix"),
            ("analysis", "Time analysis"),
        ]

    def _on_menu_action(self, action_id: str) -> None:
        if action_id == "resize":
            self._begin_resize()
        elif action_id == "fix":
            self._toggle_lock()
        elif action_id == "analysis":
            self._open_analysis()

    def _on_pet_action(self, action_id: str) -> None:
        if action_id == "place":
            self._begin_pet_place()
        elif action_id == "size":
            self._begin_pet_size()

    def _begin_pet_place(self) -> None:
        self._set_menu_open(False)
        if not getattr(self.pet, "enabled", False):
            return
        self.pet_place_mode = True
        self.pet_size_mode = False
        self._apply_pointer_mode()
        self._update_app_label()

    def _begin_pet_size(self) -> None:
        self._set_menu_open(False)
        if not getattr(self.pet, "enabled", False):
            return
        self.pet_size_mode = True
        self.pet_place_mode = False
        self._apply_pointer_mode()
        self._update_app_label()

    def _pet_layout_offset(self) -> tuple[int, int]:
        if self.pet_offset_x is not None and self.pet_offset_y is not None:
            return int(self.pet_offset_x), int(self.pet_offset_y)
        return self._default_pet_offset()

    def _default_pet_offset(self) -> tuple[int, int]:
        atlas = getattr(self.pet, "atlas", None)
        if atlas is None:
            return 0, 0
        badge = BadgeAnchor(
            0,
            0,
            self.badge_width,
            self.badge_height,
            body_width=self._hit_body_width(),
        )
        return relative_offset(
            self.pet_placement,
            badge,
            PetSize(atlas.cell_width, atlas.cell_height),
        )

    def _follow_pet_offset(self) -> tuple[int, int] | None:
        if self.pet_offset_x is None or self.pet_offset_y is None:
            return None
        return int(self.pet_offset_x), int(self.pet_offset_y)

    def _save_pet_layout(self) -> None:
        self.config["pet_scale_percent"] = self.pet_scale_percent
        if self.pet_offset_x is not None and self.pet_offset_y is not None:
            self.config["pet_offset_x"] = int(self.pet_offset_x)
            self.config["pet_offset_y"] = int(self.pet_offset_y)
        self._save_config()

    def _on_pet_pointer(self, phase: str, x: int, y: int) -> None:
        if phase == "press":
            self._pet_press = (x, y)
            self._pet_dragging = False
            if self.pet_size_mode:
                self._pet_size_origin = (x, y, self.pet_scale_percent)
            elif self.pet_place_mode:
                self._pet_place_origin = (x, y, self._pet_layout_offset())
            elif self.position_locked:
                self._pet_press = None
            else:
                self.drag_offset = (x - self.root.winfo_x(), y - self.root.winfo_y())
            return
        if phase == "drag":
            if self.pet_size_mode:
                self._drag_pet_size(x, y)
            elif self.pet_place_mode:
                self._drag_pet_place(x, y)
            elif self._pet_press is not None and not self.position_locked:
                if not self._pet_dragging:
                    origin_x, origin_y = self._pet_press
                    dx = x - origin_x
                    dy = y - origin_y
                    if dx * dx + dy * dy < self.DRAG_THRESHOLD_PX ** 2:
                        return
                    self._pet_dragging = True
                    self._body_dragging = True
                    self._set_menu_open(False)
                    self._draw_control_strip()
                self._move_to_pointer(x, y)
            return
        if self.pet_size_mode or self.pet_place_mode:
            if self._pet_dragging or self._pet_size_origin or self._pet_place_origin:
                self._save_pet_layout()
            self.pet_size_mode = False
            self.pet_place_mode = False
            self._pet_size_origin = None
            self._pet_place_origin = None
            self._pet_dragging = False
            self._pet_press = None
            self._apply_pointer_mode()
            self._update_app_label()
            return
        if self._pet_dragging:
            self._pet_dragging = False
            self._body_dragging = False
            self._save_position()
            self._draw_control_strip()
        self._pet_press = None

    def _drag_pet_place(self, x: int, y: int) -> None:
        if self._pet_place_origin is None:
            return
        start_x, start_y, (offset_x, offset_y) = self._pet_place_origin
        self._pet_dragging = True
        self.pet_offset_x = offset_x + (x - start_x)
        self.pet_offset_y = offset_y + (y - start_y)
        self._set_position(self.root.winfo_x(), self.root.winfo_y())

    def _drag_pet_size(self, x: int, y: int) -> None:
        if self._pet_size_origin is None or self.pet.atlas is None:
            return
        start_x, start_y, start_percent = self._pet_size_origin
        delta = ((x - start_x) + (y - start_y)) // 2
        percent = normalize_scale_percent(start_percent + delta)
        if percent == self.pet_scale_percent:
            return
        old = PetSize(self.pet.atlas.cell_width, self.pet.atlas.cell_height)
        self.pet_scale_percent = percent
        self.pet.set_scale_percent(percent)
        if self.pet.atlas is None:
            return
        new = PetSize(self.pet.atlas.cell_width, self.pet.atlas.cell_height)
        if self.pet_offset_x is not None and self.pet_offset_y is not None:
            self.pet_offset_x, self.pet_offset_y = keep_sit_offset(
                old, new, (self.pet_offset_x, self.pet_offset_y)
            )
        self._pet_dragging = True
        self._set_position(self.root.winfo_x(), self.root.winfo_y())

    def _toggle_lock(self) -> None:
        self.position_locked = not self.position_locked
        self.config["position_locked"] = self.position_locked
        self._save_config()
        self._set_menu_open(False)
        self._apply_theme()
        self._apply_pointer_mode()
        self._apply_layout_metrics()
        self._update_app_label()
        if hasattr(self, "overlay_hwnd"):
            self._set_position(self.root.winfo_x(), self.root.winfo_y())

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

    def _set_menu_open(self, open_: bool) -> None:
        self.menu_open = open_
        if open_:
            self._sync_menu()
            self._attach_owned_overlays()
            if hasattr(self, "overlay_hwnd"):
                self._set_position(self.root.winfo_x(), self.root.winfo_y())
            self.menu.show()
        else:
            self.menu.hide()
        self._update_edit_icon()
        self._raise_edit_control()

    def _sync_menu(self) -> None:
        if not hasattr(self, "menu"):
            return
        self.menu.set_actions(self._menu_actions())
        self.menu.apply_chrome(
            fill=self.list_background_color,
            text=self.text_color,
            muted=self.secondary_text_color,
            border=self.border_color,
            radius=self.corner_radius,
            background=self.background_color,
            list_background=self.list_background_color,
        )

    def _begin_resize(self) -> None:
        self._set_menu_open(False)
        self.move_mode = False
        self.resize_mode = True
        self._set_click_through(False)
        self._apply_theme()
        self.canvas.configure(cursor="sizing")
        self.canvas.itemconfigure(self.resize_handle, state="normal")
        self._update_app_label()

    def _apply_colour_theme(self, theme_id: str) -> None:
        theme = theme_by_id(theme_id)
        if theme is None:
            return
        self.background_color = theme.background
        self.list_background_color = theme.list_background
        self.text_color = theme.text
        self.border_color = theme.border
        self.config["background_color"] = theme.background
        self.config["list_background_color"] = theme.list_background
        self.config["text_color"] = theme.text
        self.config["border_color"] = theme.border
        self.config["colour_theme"] = theme.id
        self._apply_theme()
        self._save_config()

    def _set_corner_radius(self, radius: int) -> None:
        self.corner_radius = bounded_int(
            radius, DEFAULT_CORNER_RADIUS, MIN_CORNER_RADIUS, MAX_CORNER_RADIUS
        )
        self.config["corner_radius"] = self.corner_radius
        self._save_config()
        self._apply_theme()
        self._apply_layout_metrics()
        if hasattr(self, "overlay_hwnd"):
            self._set_position(self.root.winfo_x(), self.root.winfo_y())

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
        matched = matching_theme_id(
            self.background_color,
            self.list_background_color,
            self.text_color,
            self.border_color,
        )
        if matched:
            self.config["colour_theme"] = matched
        else:
            self.config.pop("colour_theme", None)
        self._apply_theme()
        self._save_config()

    def _apply_theme(self) -> None:
        blend_base = self._blend_base()
        self.secondary_text_color = blend_hex(blend_base, self.text_color, 0.68)
        self.hover_color = blend_hex(blend_base, self.text_color, 0.12)
        self.root.attributes("-transparentcolor", TRANSPARENT_KEY)
        self.root.configure(bg=TRANSPARENT_KEY)
        self.canvas.configure(
            bg=TRANSPARENT_KEY,
            highlightthickness=0,
            highlightbackground=self.border_color,
        )
        self.canvas.itemconfigure(self.app_text, fill=self.secondary_text_color)
        self.canvas.itemconfigure(self.title_text, fill=self.text_color)
        self.edit_window.attributes("-transparentcolor", TRANSPARENT_KEY)
        self.edit_window.configure(bg=TRANSPARENT_KEY)
        self.edit_canvas.configure(bg=TRANSPARENT_KEY)
        self._draw_badge_chrome()
        self._update_edit_icon()
        self._sync_hit_catcher()
        if hasattr(self, "list_bar"):
            self.list_bar.apply_theme(
                background=self.list_background_color,
                text=self.text_color,
                muted=self.secondary_text_color,
                border=self.border_color,
            )
        self._sync_menu()

    def _draw_badge_chrome(self) -> None:
        self.canvas.delete("chrome")
        ghost = is_transparent(self.background_color) and not self.resize_mode
        hide_border = ghost and self.position_locked
        fill = TRANSPARENT_KEY if ghost else paint_color(self.background_color)
        outline = fill if hide_border else self.border_color
        body_w = self._hit_body_width() + 1
        radius = self.corner_radius
        if radius <= 0:
            self.canvas.create_rectangle(
                0,
                0,
                body_w,
                self.badge_height,
                fill=fill,
                outline=outline,
                width=1 if outline != fill else 0,
                tags="chrome",
            )
        else:
            draw_rounded_panel(
                self.canvas,
                1,
                1,
                body_w,
                self.badge_height - 1,
                fill=fill,
                outline=outline,
                radius=radius,
                nw=True,
                ne=False,
                se=False,
                sw=True,
                width=1 if outline != fill else 0,
                tags="chrome",
            )
        try:
            self.canvas.tag_lower("chrome")
        except tk.TclError:
            pass

    def _quit(self) -> None:
        self._cancel_press_job()
        self.dwell.close("shutdown")
        if self._edit_dragging or self._body_dragging or self.resize_mode:
            self._save_position()
        if self.pet_place_mode or self.pet_size_mode:
            self._save_pet_layout()
        self.root.destroy()

    def _end_interaction(self) -> None:
        self._save_position()
        if self.pet_place_mode or self.pet_size_mode:
            self._save_pet_layout()
        self.move_mode = False
        self.resize_mode = False
        self.pet_place_mode = False
        self.pet_size_mode = False
        self._pet_size_origin = None
        self._pet_place_origin = None
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
        radius = self.corner_radius
        outline = tab_fill if ghost else self.border_color

        def paint_back(fill: str) -> None:
            if ghost:
                return
            if radius <= 0:
                canvas.create_rectangle(
                    0,
                    0,
                    strip_width,
                    height,
                    fill=fill,
                    outline=outline,
                )
                return
            draw_rounded_panel(
                canvas,
                0,
                1,
                strip_width - 1,
                height - 1,
                fill=fill,
                outline=outline,
                radius=radius,
                nw=False,
                ne=True,
                se=True,
                sw=False,
                width=1,
            )

        def paint_tab_fill(x0: int, x1: int, last: bool) -> None:
            if ghost:
                return
            if last and radius > 0:
                draw_rounded_panel(
                    canvas,
                    x0,
                    1,
                    strip_width - 1,
                    height - 1,
                    fill=self.hover_color,
                    outline=self.hover_color,
                    radius=radius,
                    nw=False,
                    ne=True,
                    se=True,
                    sw=False,
                    width=0,
                )
                return
            canvas.create_rectangle(
                x0,
                1 if radius > 0 else 0,
                x1 if not last else strip_width,
                height - (1 if radius > 0 else 0),
                fill=self.hover_color,
                outline=self.hover_color,
            )

        if self.position_locked:
            hovered = self.hovered_tab == 0
            fill = tab_fill
            if not ghost and hovered:
                fill = self.hover_color
            paint_back(fill)
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
        paint_back(tab_fill)
        for index in range(self.TAB_COUNT):
            x0 = index * self.TAB_WIDTH
            x1 = x0 + self.TAB_WIDTH
            hovered = self.hovered_tab == index
            active = (index == 0 and (editing or moving or self.menu_open)) or (
                index == 1 and list_open
            )
            if not ghost and (hovered or active):
                paint_tab_fill(x0, x1, index == self.TAB_COUNT - 1)
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

    def _update_app_label(self) -> None:
        if self.resize_mode:
            prefix = "RESIZE MODE · "
        elif self.pet_place_mode:
            prefix = "PET PLACE · "
        elif self.pet_size_mode:
            prefix = "PET SIZE · "
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
            list_radius = (
                0
                if self.corner_radius == 0
                else max(8, self.corner_radius)
            )
            self.list_bar.apply_layout(
                font_size=self.layout.list_font_size,
                count_font_size=self.layout.list_count_font_size,
                header_height=self.layout.list_header_height,
                row_height=self.layout.list_row_height,
                section_height=self.layout.list_section_height,
                max_body=self.layout.list_max_body,
                radius=list_radius,
                tail_height=self.layout.list_tail_height,
                rod_height=self.layout.list_rod_height,
                chrome_pad=self.layout.list_chrome_pad,
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
        self._draw_badge_chrome()
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
        if self.pet_place_mode or self.pet_size_mode:
            self.pet_place_mode = False
            self.pet_size_mode = False
            self._pet_size_origin = None
            self._pet_place_origin = None
            self._apply_pointer_mode()
            self._update_app_label()
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
        if hasattr(self, "menu"):
            menu_x = x + self.badge_width - self.menu.width
            self.menu.set_position(menu_x, menu_y)
        if hasattr(self, "pet"):
            self.pet.follow(
                x,
                y,
                self.badge_width,
                self.badge_height,
                body_width=self._hit_body_width(),
                offset=self._follow_pet_offset(),
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
        if (
            getattr(self, "pet", None)
            and self.pet.enabled
            and self.pet.atlas is not None
        ):
            offset_y = self._pet_layout_offset()[1]
            if offset_y < 0:
                y = max(y, work.top - offset_y + 8)
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
            self.pet.hwnd,
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
                label=resolved.list_label,
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
