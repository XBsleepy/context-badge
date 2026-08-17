"""Optional per-tab todo panel shown under the badge from the List tab."""

from __future__ import annotations

import tkinter as tk
from collections.abc import Callable
from typing import Any

from .bubble import content_box, draw_scroll_bubble, unfold_ease
from .list_store import BASE_LIST_KEY, ListStore, list_key, next_row_after_enter
from .theme import TRANSPARENT_KEY, blend_hex, is_transparent, paint_color
from .win32 import (
    GWL_EXSTYLE,
    HWND_TOPMOST,
    SWP_FRAMECHANGED,
    SWP_NOACTIVATE,
    SWP_NOMOVE,
    SWP_NOSIZE,
    SWP_SHOWWINDOW,
    SW_HIDE,
    WS_EX_LAYERED,
    WS_EX_NOACTIVATE,
    WS_EX_TOOLWINDOW,
    WS_EX_TRANSPARENT,
    user32,
)

HEADER_HEIGHT = 40
ROW_HEIGHT = 44
SECTION_HEIGHT = 26
MAX_BODY_HEIGHT = 264
GAP_FROM_BADGE = 0
EDIT_NEW = "__new__"
RADIUS = 18
TAIL_HEIGHT = 11
ROD_HEIGHT = 8
CHROME_PAD = 10
BG = "#101218"
TEXT = "#f4f1ea"
MUTED = "#aab3c2"
DONE = "#6b7380"
ROW = "#1a1d24"
CHECK_WELL = "#3a3f4a"
BASE_HINT = "Here you can keep items that stay with you"
NOTE_HINT = "Here you can write a note for this place"
ITEM_HINT = "Here you can add an item"

_NAV_KEYS = {
    "Return",
    "KP_Enter",
    "Tab",
    "Escape",
    "BackSpace",
    "Delete",
    "Left",
    "Right",
    "Up",
    "Down",
    "Home",
    "End",
    "Shift_L",
    "Shift_R",
    "Control_L",
    "Control_R",
    "Alt_L",
    "Alt_R",
}


def _is_typing_key(event: tk.Event) -> bool:
    """Return whether this key should replace a placeholder."""
    if event.keysym in _NAV_KEYS:
        return False
    char = event.char or ""
    return len(char) == 1 and char.isprintable()


class ListBar:
    """A topmost todo panel for the current foreground tab."""

    def __init__(
        self,
        parent: tk.Misc,
        store: ListStore,
        *,
        expanded: bool = False,
        on_expand_changed: Callable[[bool], None] | None = None,
        on_geometry_changed: Callable[[], None] | None = None,
    ) -> None:
        self.store = store
        self.expanded = bool(expanded)
        self.on_expand_changed = on_expand_changed
        self.on_geometry_changed = on_geometry_changed
        self._key = ""
        self._surface = "Starting…"
        self._base_items: list[dict[str, Any]] = []
        self._items: list[dict[str, Any]] = []
        self._vars: list[tk.BooleanVar] = []
        self._editing: str | None = None
        self._editing_key = ""
        self._hidden = False
        self._mapped = False
        self._x = 0
        self._y = 0
        self._width = 280
        self._transparent = False
        self._panel_bg = BG
        self._row_bg = ROW
        self._text = TEXT
        self._muted = MUTED
        self._border = "#4b5568"
        self._note_placeholder = True
        self._font_size = 13
        self._count_font_size = 10
        self._header_height = HEADER_HEIGHT
        self._row_height = ROW_HEIGHT
        self._section_height = SECTION_HEIGHT
        self._max_body = MAX_BODY_HEIGHT
        self._radius = RADIUS
        self._tail_height = TAIL_HEIGHT
        self._rod_height = ROD_HEIGHT
        self._chrome_pad = CHROME_PAD
        self._unfold = 1.0 if self.expanded else 0.0
        self._anim_job: str | None = None
        self._anim_target = self._unfold
        self._anim_hide = False

        self.window = tk.Toplevel(parent)
        self.window.title("Context Badge list")
        self.window.overrideredirect(True)
        self.window.attributes("-topmost", True)
        self.window.configure(bg=TRANSPARENT_KEY)
        self.window.geometry(f"{self._width}x{HEADER_HEIGHT}+0+0")

        self.chrome = tk.Canvas(
            self.window,
            bg=TRANSPARENT_KEY,
            highlightthickness=0,
            bd=0,
        )
        self.content = tk.Frame(self.window, bg=BG)

        self.base_block = tk.Frame(self.content, bg=BG)
        self.base_rows = tk.Frame(self.base_block, bg=ROW)
        self.base_rows.pack(fill="x")
        self.base_rule = tk.Frame(self.base_block, bg="#3a3f4a", height=1)
        self.base_rule.pack(fill="x")
        self.base_block.bind("<MouseWheel>", self._on_mousewheel)
        self.base_rows.bind("<MouseWheel>", self._on_mousewheel)

        self.header = tk.Frame(self.content, bg=BG, height=HEADER_HEIGHT)
        self.header.pack_propagate(False)
        self.note_var = tk.StringVar()
        self.note_entry = tk.Entry(
            self.header,
            textvariable=self.note_var,
            bg=BG,
            fg=MUTED,
            insertbackground=TEXT,
            relief="flat",
            font=("Segoe UI Semibold", self._font_size),
            highlightthickness=0,
            bd=0,
        )
        self.note_entry.pack(side="left", fill="x", expand=True, padx=(12, 0))
        self.note_entry.bind("<FocusIn>", self._on_note_focus_in)
        self.note_entry.bind("<ButtonRelease-1>", self._on_note_focus_in)
        self.note_entry.bind("<FocusOut>", self._on_note_focus_out)
        self.note_entry.bind("<Return>", self._on_note_return)
        self.note_entry.bind("<KeyPress>", self._on_note_key)
        self.note_entry.bind("<<Paste>>", self._on_note_paste)
        self.count_label = tk.Label(
            self.header,
            text="",
            bg=BG,
            fg=MUTED,
            font=("Segoe UI", self._count_font_size),
        )
        self.count_label.pack(side="right", padx=(4, 12))

        self.body = tk.Frame(self.content, bg=BG)
        self.canvas = tk.Canvas(
            self.body,
            bg=ROW,
            highlightthickness=0,
            bd=0,
        )
        self.scroll = tk.Scrollbar(
            self.body, orient="vertical", command=self.canvas.yview
        )
        self.canvas.configure(yscrollcommand=self.scroll.set)
        self.rows = tk.Frame(self.canvas, bg=ROW)
        self._rows_window = self.canvas.create_window((0, 0), window=self.rows, anchor="nw")
        self.rows.bind("<Configure>", self._on_rows_configure)
        self.canvas.bind("<Configure>", self._on_canvas_configure)
        self.canvas.bind("<MouseWheel>", self._on_mousewheel)
        self.rows.bind("<MouseWheel>", self._on_mousewheel)
        self.header.bind("<MouseWheel>", self._on_mousewheel)
        self.content.bind("<MouseWheel>", self._on_mousewheel)
        self.chrome.bind("<MouseWheel>", self._on_mousewheel)

        self.window.update_idletasks()
        inner = self.window.winfo_id()
        self.hwnd = user32.GetParent(inner) or inner
        self._apply_window_style()
        self.window.attributes("-transparentcolor", TRANSPARENT_KEY)
        self.window.withdraw()
        self._sync_body()
        self._reload()

    def apply_theme(
        self,
        *,
        background: str,
        text: str,
        muted: str,
        border: str = "",
    ) -> None:
        """Paint the panel from its own fill, including the transparent swatch."""
        self._text = text
        self._muted = muted
        self._transparent = is_transparent(background)
        panel = paint_color(background, BG)
        row = (
            TRANSPARENT_KEY
            if self._transparent
            else blend_hex(panel, "#000000", 0.14)
        )
        if (
            isinstance(border, str)
            and border.startswith("#")
            and len(border) == 7
        ):
            self._border = border
        else:
            self._border = blend_hex(panel, text, 0.28)
        self._panel_bg = panel
        self._row_bg = row
        self.window.attributes("-transparentcolor", TRANSPARENT_KEY)
        self.window.configure(bg=TRANSPARENT_KEY)
        self.chrome.configure(bg=TRANSPARENT_KEY)
        inner = TRANSPARENT_KEY if self._transparent else panel
        self.content.configure(bg=inner)
        self.header.configure(bg=inner, height=self._header_height)
        self.note_entry.configure(
            bg=inner,
            fg=self._muted if self._note_placeholder else self._text,
            insertbackground=self._text,
            font=("Segoe UI Semibold", self._font_size),
        )
        self.count_label.configure(
            bg=inner,
            fg=self._muted,
            font=("Segoe UI", self._count_font_size),
        )
        self.body.configure(bg=inner)
        self.base_block.configure(bg=inner)
        self.base_rows.configure(bg=row)
        self.base_rule.configure(
            bg=TRANSPARENT_KEY if self._transparent else blend_hex(panel, text, 0.16)
        )
        self.canvas.configure(bg=row)
        self.rows.configure(bg=row)
        if self.expanded:
            self._sync_body()
            self._render_rows()
            self._refresh_header()
            self._apply_geometry()

    def apply_layout(
        self,
        *,
        font_size: int,
        count_font_size: int,
        header_height: int,
        row_height: int,
        section_height: int,
        max_body: int,
        radius: int,
        tail_height: int,
        rod_height: int,
        chrome_pad: int,
    ) -> None:
        """Follow the badge height so list type and rows stay in proportion."""
        self._font_size = int(font_size)
        self._count_font_size = int(count_font_size)
        self._header_height = int(header_height)
        self._row_height = int(row_height)
        self._section_height = int(section_height)
        self._max_body = int(max_body)
        self._radius = int(radius)
        self._tail_height = int(tail_height)
        self._rod_height = int(rod_height)
        self._chrome_pad = int(chrome_pad)
        self.header.configure(height=self._header_height)
        self.note_entry.configure(font=("Segoe UI Semibold", self._font_size))
        self.count_label.configure(font=("Segoe UI", self._count_font_size))
        if self.expanded:
            self._render_rows()
            self._apply_geometry()
            if self.on_geometry_changed:
                self.on_geometry_changed()

    def _apply_window_style(self) -> None:
        style = user32.GetWindowLongW(self.hwnd, GWL_EXSTYLE)
        style |= WS_EX_LAYERED | WS_EX_TOOLWINDOW
        style &= ~WS_EX_TRANSPARENT
        style &= ~WS_EX_NOACTIVATE
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

    def _base_height(self) -> int:
        return (len(self._base_items) + 1) * self._row_height + 1

    def _chrome_height(self) -> int:
        return (
            self._tail_height
            + self._rod_height
            + self._chrome_pad
            + self._rod_height
            + self._chrome_pad
        )

    def _paper_height(self) -> int:
        window_rows = max(self._row_height, (len(self._items) + 1) * self._row_height)
        window_body = min(self._max_body, window_rows)
        return self._base_height() + self._header_height + window_body

    def height(self) -> int:
        if not self.expanded and self._unfold <= 0:
            return 0
        full = self._chrome_height() + self._paper_height()
        chrome = self._chrome_height()
        return max(chrome, round(chrome + (full - chrome) * unfold_ease(self._unfold)))

    def set_key(
        self,
        executable: str,
        surface: str,
        *,
        label: str | None = None,
    ) -> None:
        key = list_key(executable, surface)
        header = (label or surface).strip() or "Untitled window"
        if key != self._key and self._note_entry_focused():
            self._commit_note(refresh=False)
        display = self._list_display_name(key, header)
        if key == self._key:
            if display != self._surface:
                self._surface = display
                self._refresh_header()
            return
        if self._editing_key != BASE_LIST_KEY:
            self._editing = None
            self._editing_key = ""
        self._key = key
        self._surface = display
        try:
            self.store.ensure_label(key, header)
        except OSError:
            pass
        self._reload()

    def _list_display_name(self, key: str, header: str) -> str:
        stored = ""
        try:
            stored = self.store.label(key)
        except OSError:
            stored = ""
        return stored or header or "Untitled window"

    def _reload(self) -> None:
        try:
            self._base_items = self.store.items(BASE_LIST_KEY)
        except OSError:
            self._base_items = []
        try:
            self._items = self.store.items(self._key) if self._key else []
        except OSError:
            self._items = []
        self._refresh_header()
        if self.expanded:
            self._render_rows()
            self._apply_geometry()
            if self.on_geometry_changed:
                self.on_geometry_changed()

    def toggle(self) -> None:
        self.set_expanded(not self.expanded)

    def set_expanded(self, expanded: bool) -> None:
        expanded = bool(expanded)
        if expanded == self.expanded and self._anim_job is None:
            return
        self._cancel_anim()
        if expanded:
            self.expanded = True
            self._anim_hide = False
            self._sync_body()
            self._refresh_header()
            self._render_rows()
            if self._unfold <= 0:
                self._unfold = 0.0
            self._animate_to(1.0)
            if self.on_expand_changed:
                self.on_expand_changed(True)
            return
        if self._unfold <= 0:
            self._finish_collapse()
            return
        self._animate_to(0.0, hide=True)

    def _cancel_anim(self) -> None:
        if self._anim_job is not None:
            try:
                self.window.after_cancel(self._anim_job)
            except tk.TclError:
                pass
            self._anim_job = None

    def _animate_to(self, target: float, *, hide: bool = False) -> None:
        self._anim_target = 1.0 if target >= 1 else 0.0
        self._anim_hide = hide
        self._tick_anim()

    def _tick_anim(self) -> None:
        self._apply_geometry()
        if self.on_geometry_changed:
            self.on_geometry_changed()
        target = self._anim_target
        if abs(self._unfold - target) <= 1e-6:
            self._anim_job = None
            self._unfold = target
            if self._anim_hide:
                self._finish_collapse()
            return
        step = 0.14
        if self._unfold < target:
            self._unfold = min(target, self._unfold + step)
        else:
            self._unfold = max(target, self._unfold - step)
        self._anim_job = self.window.after(16, self._tick_anim)

    def _finish_collapse(self) -> None:
        self._cancel_anim()
        self._unfold = 0.0
        self._anim_hide = False
        self.expanded = False
        self._sync_body()
        self._apply_geometry()
        if self.on_expand_changed:
            self.on_expand_changed(False)
        if self.on_geometry_changed:
            self.on_geometry_changed()

    def set_position(self, x: int, y: int, width: int) -> None:
        self._x = int(x)
        self._y = int(y)
        self._width = max(160, int(width))
        self._refresh_header()
        self._apply_geometry()

    def hide(self) -> None:
        self._cancel_anim()
        if self.expanded:
            self._unfold = 1.0
        self._hidden = True
        self._mapped = False
        user32.ShowWindow(self.hwnd, SW_HIDE)
        self.window.withdraw()

    def show(self) -> None:
        self._hidden = False
        self._apply_geometry()

    def raise_bar(self) -> None:
        if self._hidden or not self.expanded:
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

    def _apply_geometry(self) -> None:
        if self._hidden or not self.expanded:
            if self._mapped:
                user32.ShowWindow(self.hwnd, SW_HIDE)
                self.window.withdraw()
                self._mapped = False
            return
        height = self.height()
        self.window.geometry(f"{self._width}x{height}+{self._x}+{self._y}")
        if not self._mapped:
            self.window.deiconify()
            self._mapped = True
            self._apply_window_style()
        user32.SetWindowPos(
            self.hwnd,
            HWND_TOPMOST,
            self._x,
            self._y,
            self._width,
            height,
            SWP_NOACTIVATE | SWP_SHOWWINDOW,
        )
        self._layout_chrome(self._width, height)
        x, y, inner_w, inner_h = content_box(
            self._width,
            height,
            tail_height=self._tail_height,
            radius=self._radius,
            rod_height=self._rod_height,
            pad=self._chrome_pad,
        )
        self.content.place(x=x, y=y, width=inner_w, height=inner_h)
        self.content.lift()
        canvas_height = max(self._row_height, inner_h - self._header_height - self._base_height())
        self.canvas.configure(width=max(80, inner_w), height=canvas_height)
        self.canvas.itemconfigure(self._rows_window, width=max(80, inner_w))

    def _layout_chrome(self, width: int, height: int) -> None:
        self.chrome.place(x=0, y=0, width=width, height=height)
        fill = TRANSPARENT_KEY if self._transparent else self._panel_bg
        highlight = (
            TRANSPARENT_KEY
            if self._transparent
            else blend_hex(self._panel_bg, "#ffffff", 0.22)
        )
        rod = (
            TRANSPARENT_KEY
            if self._transparent
            else blend_hex(self._panel_bg, self._text, 0.16)
        )
        draw_scroll_bubble(
            self.chrome,
            width,
            height,
            fill=fill,
            border=self._border,
            highlight=highlight,
            rod_fill=rod,
            radius=self._radius,
            tail_height=self._tail_height,
            tail_width=max(16, self._tail_height * 2),
            rod_height=self._rod_height,
        )

    def _sync_body(self) -> None:
        self.canvas.pack_forget()
        self.scroll.pack_forget()
        self.body.pack_forget()
        self.base_block.pack_forget()
        self.header.pack_forget()
        self.content.place_forget()
        self.chrome.place_forget()
        if not self.expanded:
            return
        self.base_block.pack(fill="x")
        self.header.pack(fill="x")
        self.body.pack(fill="both", expand=True)
        self.canvas.pack(side="left", fill="both", expand=True)

    def _note_entry_focused(self) -> bool:
        try:
            return self.window.focus_get() is self.note_entry
        except tk.TclError:
            return False

    def _refresh_header(self) -> None:
        if self._note_entry_focused():
            self._refresh_count()
            return
        note = ""
        if self._key:
            try:
                note = self.store.note(self._key)
            except OSError:
                note = ""
        if note:
            self._note_placeholder = False
            self.note_var.set(note)
            self.note_entry.configure(fg=self._text)
        else:
            self._note_placeholder = True
            self.note_var.set(NOTE_HINT)
            self.note_entry.configure(fg=self._muted)
        self._refresh_count()

    def _refresh_count(self) -> None:
        open_count = sum(1 for item in self._items if not item["done"])
        if not self._items:
            self.count_label.configure(text="")
        elif open_count:
            self.count_label.configure(text=f"{open_count} left")
        else:
            self.count_label.configure(text="done")

    def _on_note_focus_in(self, _event: tk.Event) -> None:
        if self._note_placeholder:
            self.note_entry.selection_range(0, "end")

    def _on_note_key(self, event: tk.Event) -> str | None:
        if not self._note_placeholder:
            return None
        if event.keysym in {"BackSpace", "Delete"}:
            return "break"
        if not _is_typing_key(event):
            return None
        self._note_placeholder = False
        try:
            selected = bool(self.note_entry.selection_present())
        except tk.TclError:
            selected = False
        if not selected:
            self.note_var.set("")
        self.note_entry.configure(fg=self._text)
        return None

    def _on_note_paste(self, _event: tk.Event) -> None:
        if not self._note_placeholder:
            return
        self._note_placeholder = False
        self.note_var.set("")
        self.note_entry.configure(fg=self._text)

    def _on_note_focus_out(self, _event: tk.Event) -> None:
        self._commit_note()

    def _on_note_return(self, _event: tk.Event) -> str:
        self._commit_note()
        self.window.focus_set()
        return "break"

    def _commit_note(self, *, refresh: bool = True) -> None:
        if not self._key:
            if refresh:
                self._refresh_header()
            return
        text = "" if self._note_placeholder else self.note_var.get().strip()
        try:
            self.store.set_note(self._key, text)
        except OSError:
            pass
        if refresh:
            self._refresh_header()

    def _render_rows(self) -> None:
        self._vars = []
        self._fill_section(
            self.base_rows,
            BASE_LIST_KEY,
            self._base_items,
            empty_hint=BASE_HINT,
        )
        self._fill_section(
            self.rows,
            self._key,
            self._items,
            empty_hint=ITEM_HINT,
        )
        self.base_rows.update_idletasks()
        self.rows.update_idletasks()
        self.canvas.configure(scrollregion=self.canvas.bbox("all") or (0, 0, 0, 0))

    def _fill_section(
        self,
        parent: tk.Frame,
        key: str,
        items: list[dict[str, Any]],
        *,
        empty_hint: str = "",
    ) -> None:
        for child in parent.winfo_children():
            child.destroy()
        for item in items:
            self._build_row(parent, key, item)
        self._build_empty_row(parent, key, hint=empty_hint)

    def _item_hint(self, key: str) -> str:
        return BASE_HINT if key == BASE_LIST_KEY else ITEM_HINT

    def _build_row(self, parent: tk.Frame, key: str, item: dict[str, Any]) -> None:
        row_bg = self._row_bg
        panel_bg = self._panel_bg
        row = tk.Frame(parent, bg=row_bg, height=self._row_height)
        row.pack(fill="x")
        row.pack_propagate(False)
        row.bind("<MouseWheel>", self._on_mousewheel)
        done_var = tk.BooleanVar(value=bool(item["done"]))
        self._vars.append(done_var)
        check = tk.Checkbutton(
            row,
            variable=done_var,
            bg=row_bg,
            activebackground=row_bg,
            selectcolor=CHECK_WELL if self._transparent else panel_bg,
            fg=self._text,
            highlightthickness=0,
            bd=0,
            command=lambda item_id=item["id"], var=done_var, store_key=key: self._toggle_done(
                store_key, item_id, var
            ),
        )
        check.pack(side="left", padx=(8, 2))
        if self._editing_key == key and self._editing == item["id"]:
            self._pack_item_entry(
                row, key, item["id"], item["text"], hint=self._item_hint(key)
            )
        else:
            colour = DONE if item["done"] else self._text
            text = item["text"] or self._item_hint(key)
            label = tk.Label(
                row,
                text=text,
                bg=row_bg,
                fg=colour if item["text"] else self._muted,
                font=("Segoe UI", self._font_size, "overstrike" if item["done"] else "normal"),
                anchor="w",
                cursor="xterm",
            )
            label.pack(side="left", fill="x", expand=True)
            label.bind("<MouseWheel>", self._on_mousewheel)
            label.bind(
                "<Button-1>",
                lambda _event, store_key=key, item_id=item["id"]: self._begin_edit(
                    store_key, item_id
                ),
            )
        delete = tk.Label(
            row,
            text="×",
            bg=row_bg,
            fg=self._muted,
            font=("Segoe UI Semibold", max(11, self._font_size + 2)),
            cursor="hand2",
            padx=8,
        )
        delete.pack(side="right")
        delete.bind(
            "<Button-1>",
            lambda _event, store_key=key, item_id=item["id"]: self._delete_item(
                store_key, item_id
            ),
        )

    def _build_empty_row(
        self, parent: tk.Frame, key: str, *, hint: str = ""
    ) -> None:
        row = tk.Frame(parent, bg=self._row_bg, height=self._row_height)
        row.pack(fill="x")
        row.pack_propagate(False)
        row.bind("<MouseWheel>", self._on_mousewheel)
        spacer = tk.Label(
            row,
            text="",
            bg=self._row_bg,
            width=3,
        )
        spacer.pack(side="left", padx=(8, 2))
        spacer.bind("<MouseWheel>", self._on_mousewheel)
        if self._editing_key == key and self._editing == EDIT_NEW:
            self._pack_item_entry(row, key, EDIT_NEW, "", hint=hint)
            return
        label = tk.Label(
            row,
            text=hint,
            bg=self._row_bg,
            fg=self._muted,
            font=("Segoe UI", self._font_size),
            anchor="w",
            cursor="xterm",
        )
        label.pack(side="left", fill="x", expand=True)
        label.bind("<MouseWheel>", self._on_mousewheel)
        for widget in (row, spacer, label):
            widget.configure(cursor="xterm")
            widget.bind(
                "<Button-1>",
                lambda _event, store_key=key: self._begin_new(store_key),
            )

    def _pack_item_entry(
        self,
        row: tk.Frame,
        key: str,
        item_id: str,
        text: str,
        *,
        hint: str = "",
    ) -> tk.Entry:
        hint_on = [bool(hint) and not str(text).strip()]
        entry = tk.Entry(
            row,
            bg=self._panel_bg,
            fg=self._muted if hint_on[0] else self._text,
            insertbackground=self._text,
            relief="flat",
            font=("Segoe UI", self._font_size),
        )
        entry.insert(0, hint if hint_on[0] else text)
        entry.pack(side="left", fill="x", expand=True, padx=(0, 4), pady=4)
        entry.focus_set()
        if hint_on[0]:
            entry.selection_range(0, "end")

        def real_value() -> str:
            if hint_on[0]:
                return ""
            return entry.get().strip()

        entry._real_value = real_value  # type: ignore[attr-defined]

        def on_key(event: tk.Event) -> str | None:
            if not hint_on[0]:
                return None
            if event.keysym in {"BackSpace", "Delete"}:
                return "break"
            if not _is_typing_key(event):
                return None
            hint_on[0] = False
            try:
                selected = bool(entry.selection_present())
            except tk.TclError:
                selected = False
            if not selected:
                entry.delete(0, "end")
            entry.configure(fg=self._text)
            return None

        def on_paste(_event: tk.Event) -> None:
            if not hint_on[0]:
                return
            hint_on[0] = False
            entry.delete(0, "end")
            entry.configure(fg=self._text)

        entry.bind("<KeyPress>", on_key)
        entry.bind("<<Paste>>", on_paste)
        entry.bind(
            "<Return>",
            lambda _event, store_key=key, current=item_id, field=entry: self._on_item_return(
                store_key, current, field
            ),
        )
        entry.bind(
            "<KP_Enter>",
            lambda _event, store_key=key, current=item_id, field=entry: self._on_item_return(
                store_key, current, field
            ),
        )
        entry.bind(
            "<FocusOut>",
            lambda _event, store_key=key, current=item_id, field=entry: self._commit_text(
                store_key, current, field
            ),
        )
        entry.bind("<Escape>", lambda _event: self._cancel_edit())
        return entry

    def _on_item_return(self, key: str, item_id: str, field: tk.Entry) -> str:
        self._commit_text(key, item_id, field, advance=True)
        return "break"

    def _begin_edit(self, key: str, item_id: str) -> None:
        if not key:
            return
        self._editing_key = key
        self._editing = item_id
        self._render_rows()

    def _begin_new(self, key: str) -> None:
        if key != BASE_LIST_KEY and not self._key:
            return
        self._editing_key = key
        self._editing = EDIT_NEW
        self._render_rows()

    def _cancel_edit(self) -> None:
        self._editing = None
        self._editing_key = ""
        self._render_rows()

    def _commit_text(
        self,
        key: str,
        item_id: str,
        field: tk.Entry,
        *,
        advance: bool = False,
    ) -> None:
        if self._editing_key != key or self._editing != item_id:
            return
        getter = getattr(field, "_real_value", None)
        text = getter() if callable(getter) else field.get().strip()
        self._editing = None
        self._editing_key = ""
        store_key = BASE_LIST_KEY if key == BASE_LIST_KEY else self._key
        if not store_key:
            self._reload()
            return
        try:
            if item_id == EDIT_NEW:
                if text:
                    self.store.add_item(store_key, text)
                    if advance:
                        self._editing_key = key
                        self._editing = EDIT_NEW
            elif not text:
                self.store.delete_item(store_key, item_id)
            else:
                self.store.set_text(store_key, item_id, text)
                if advance:
                    after_id = next_row_after_enter(
                        self.store.items(store_key), item_id
                    )
                    if after_id is None:
                        self._editing_key = key
                        self._editing = EDIT_NEW
                    else:
                        created = self.store.add_item(
                            store_key, "", after_id=after_id
                        )
                        self._editing_key = key
                        self._editing = created["id"]
        except OSError:
            pass
        self._reload()

    def _toggle_done(self, key: str, item_id: str, var: tk.BooleanVar) -> None:
        if not key:
            return
        try:
            self.store.set_done(key, item_id, bool(var.get()))
        except OSError:
            pass
        self._reload()

    def _delete_item(self, key: str, item_id: str) -> None:
        if not key:
            return
        try:
            self.store.delete_item(key, item_id)
        except OSError:
            pass
        if self._editing_key == key and self._editing == item_id:
            self._editing = None
            self._editing_key = ""
        self._reload()

    def _on_rows_configure(self, _event: tk.Event) -> None:
        self.canvas.configure(scrollregion=self.canvas.bbox("all") or (0, 0, 0, 0))

    def _on_canvas_configure(self, event: tk.Event) -> None:
        self.canvas.itemconfigure(self._rows_window, width=event.width)

    def _on_mousewheel(self, event: tk.Event) -> None:
        if not self.expanded:
            return
        self.canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
