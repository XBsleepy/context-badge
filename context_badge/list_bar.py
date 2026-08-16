"""Optional per-tab todo panel shown under the badge from the List tab."""

from __future__ import annotations

import tkinter as tk
from collections.abc import Callable
from typing import Any

from .list_store import ListStore, list_key
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

HEADER_HEIGHT = 28
ROW_HEIGHT = 32
ADD_HEIGHT = 28
MAX_BODY_HEIGHT = 192
GAP_FROM_BADGE = 2
BG = "#20232a"
TEXT = "#f3f5f7"
MUTED = "#aab3c2"
ACCENT = "#8fc0ff"
DONE = "#6b7380"
ROW = "#1a1d24"
CHECK_WELL = "#3a3f4a"


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
        self._items: list[dict[str, Any]] = []
        self._vars: list[tk.BooleanVar] = []
        self._editing: str | None = None
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
        self._note_placeholder = True
        self._font_size = 9
        self._count_font_size = 8
        self._header_height = HEADER_HEIGHT
        self._row_height = ROW_HEIGHT
        self._add_height = ADD_HEIGHT

        self.window = tk.Toplevel(parent)
        self.window.title("Context Badge list")
        self.window.overrideredirect(True)
        self.window.attributes("-topmost", True)
        self.window.configure(bg=BG)
        self.window.geometry(f"{self._width}x{HEADER_HEIGHT}+0+0")

        self.header = tk.Frame(self.window, bg=BG, height=HEADER_HEIGHT)
        self.header.pack_propagate(False)
        self.note_var = tk.StringVar()
        self.note_entry = tk.Entry(
            self.header,
            textvariable=self.note_var,
            bg=BG,
            fg=MUTED,
            insertbackground=TEXT,
            relief="flat",
            font=("Segoe UI Semibold", 9),
            highlightthickness=0,
            bd=0,
        )
        self.note_entry.pack(side="left", fill="x", expand=True, padx=(12, 0))
        self.note_entry.bind("<FocusIn>", self._on_note_focus_in)
        self.note_entry.bind("<FocusOut>", self._on_note_focus_out)
        self.note_entry.bind("<Return>", self._on_note_return)
        self.count_label = tk.Label(
            self.header,
            text="",
            bg=BG,
            fg=MUTED,
            font=("Segoe UI", 8),
        )
        self.count_label.pack(side="right", padx=(4, 12))

        self.body = tk.Frame(self.window, bg=BG)
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
        self.add_button = tk.Label(
            self.body,
            text="+  Add item",
            bg=BG,
            fg=ACCENT,
            font=("Segoe UI Semibold", 9),
            anchor="w",
            cursor="hand2",
            padx=12,
            pady=4,
        )
        self.add_button.bind("<Button-1>", lambda _event: self._add_item())
        self.add_button.bind("<MouseWheel>", self._on_mousewheel)

        self.window.update_idletasks()
        inner = self.window.winfo_id()
        self.hwnd = user32.GetParent(inner) or inner
        self._apply_window_style()
        self.window.withdraw()
        if self.expanded:
            self.header.pack(fill="x")
        self._sync_body()
        self._refresh_header()

    def apply_theme(self, *, background: str, text: str, muted: str) -> None:
        """Paint the panel from its own fill, including the transparent swatch."""
        self._text = text
        self._muted = muted
        self._transparent = is_transparent(background)
        panel = paint_color(background, BG)
        row = (
            TRANSPARENT_KEY
            if self._transparent
            else blend_hex(panel, "#000000", 0.18)
        )
        self._panel_bg = panel
        self._row_bg = row
        self.window.attributes(
            "-transparentcolor", TRANSPARENT_KEY if self._transparent else ""
        )
        self.window.configure(bg=panel)
        self.header.configure(bg=panel, height=self._header_height)
        self.note_entry.configure(
            bg=panel,
            fg=self._muted if self._note_placeholder else self._text,
            insertbackground=self._text,
            font=("Segoe UI Semibold", self._font_size),
        )
        self.count_label.configure(
            bg=panel,
            fg=self._muted,
            font=("Segoe UI", self._count_font_size),
        )
        self.body.configure(bg=panel)
        self.canvas.configure(bg=row)
        self.rows.configure(bg=row)
        self.add_button.configure(
            bg=panel,
            fg=ACCENT,
            font=("Segoe UI Semibold", self._font_size),
        )
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
        add_height: int,
    ) -> None:
        """Follow the badge height so list type and rows stay in proportion."""
        self._font_size = int(font_size)
        self._count_font_size = int(count_font_size)
        self._header_height = int(header_height)
        self._row_height = int(row_height)
        self._add_height = int(add_height)
        self.header.configure(height=self._header_height)
        self.note_entry.configure(font=("Segoe UI Semibold", self._font_size))
        self.count_label.configure(font=("Segoe UI", self._count_font_size))
        self.add_button.configure(font=("Segoe UI Semibold", self._font_size))
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

    def height(self) -> int:
        if not self.expanded:
            return 0
        rows_height = max(self._row_height, len(self._items) * self._row_height)
        body = min(MAX_BODY_HEIGHT, rows_height + self._add_height)
        return self._header_height + body

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
        if key == self._key:
            if header != self._surface:
                self._surface = header
                self._refresh_header()
            return
        self._key = key
        self._surface = header
        self._editing = None
        self._reload()

    def _reload(self) -> None:
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
        if expanded == self.expanded:
            return
        self.expanded = expanded
        if self.expanded:
            self.header.pack(fill="x")
            self._sync_body()
            self._refresh_header()
            self._render_rows()
        else:
            self._sync_body()
            self.header.pack_forget()
        self._apply_geometry()
        if self.on_expand_changed:
            self.on_expand_changed(self.expanded)
        if self.on_geometry_changed:
            self.on_geometry_changed()

    def set_position(self, x: int, y: int, width: int) -> None:
        self._x = int(x)
        self._y = int(y)
        self._width = max(160, int(width))
        self._refresh_header()
        self._apply_geometry()

    def hide(self) -> None:
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
            0,
            0,
            SWP_NOSIZE | SWP_NOACTIVATE | SWP_SHOWWINDOW,
        )
        canvas_height = max(self._row_height, height - self._header_height - self._add_height)
        gutter = 8 if self._transparent else 18
        inner_width = max(80, self._width - gutter)
        self.canvas.configure(width=inner_width, height=canvas_height)
        self.canvas.itemconfigure(self._rows_window, width=inner_width)

    def _sync_body(self) -> None:
        self.canvas.pack_forget()
        self.scroll.pack_forget()
        self.add_button.pack_forget()
        self.body.pack_forget()
        if not self.expanded:
            return
        self.body.pack(fill="both", expand=True)
        self.add_button.pack(side="bottom", fill="x")
        if not self._transparent:
            self.scroll.pack(side="right", fill="y")
        self.canvas.pack(side="left", fill="both", expand=True)

    def _note_entry_focused(self) -> bool:
        try:
            return self.window.focus_get() is self.note_entry
        except tk.TclError:
            return False

    def _refresh_header(self) -> None:
        if self._note_entry_focused() and not self._note_placeholder:
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
            self.note_var.set(self._surface)
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
        for child in self.rows.winfo_children():
            child.destroy()
        self._vars = []
        for item in self._items:
            self._build_row(item)
        self.rows.update_idletasks()
        self.canvas.configure(scrollregion=self.canvas.bbox("all") or (0, 0, 0, 0))

    def _build_row(self, item: dict[str, Any]) -> None:
        row_bg = self._row_bg
        panel_bg = self._panel_bg
        row = tk.Frame(self.rows, bg=row_bg, height=self._row_height)
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
            command=lambda item_id=item["id"], var=done_var: self._toggle_done(
                item_id, var
            ),
        )
        check.pack(side="left", padx=(8, 2))
        if self._editing == item["id"]:
            entry = tk.Entry(
                row,
                bg=panel_bg,
                fg=self._text,
                insertbackground=self._text,
                relief="flat",
                font=("Segoe UI", self._font_size),
            )
            entry.insert(0, item["text"])
            entry.pack(side="left", fill="x", expand=True, padx=(0, 4), pady=4)
            entry.focus_set()
            entry.bind(
                "<Return>",
                lambda _event, item_id=item["id"], field=entry: self._commit_text(
                    item_id, field
                ),
            )
            entry.bind(
                "<FocusOut>",
                lambda _event, item_id=item["id"], field=entry: self._commit_text(
                    item_id, field
                ),
            )
            entry.bind("<Escape>", lambda _event: self._cancel_edit())
        else:
            colour = DONE if item["done"] else self._text
            label = tk.Label(
                row,
                text=item["text"] or "New item",
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
                lambda _event, item_id=item["id"]: self._begin_edit(item_id),
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
            lambda _event, item_id=item["id"]: self._delete_item(item_id),
        )

    def _begin_edit(self, item_id: str) -> None:
        self._editing = item_id
        self._render_rows()

    def _cancel_edit(self) -> None:
        self._editing = None
        self._render_rows()

    def _commit_text(self, item_id: str, field: tk.Entry) -> None:
        if self._editing != item_id:
            return
        text = field.get().strip()
        self._editing = None
        if not self._key:
            return
        try:
            if not text:
                self.store.delete_item(self._key, item_id)
            else:
                self.store.set_text(self._key, item_id, text)
        except OSError:
            pass
        self._reload()

    def _toggle_done(self, item_id: str, var: tk.BooleanVar) -> None:
        if not self._key:
            return
        try:
            self.store.set_done(self._key, item_id, bool(var.get()))
        except OSError:
            pass
        self._reload()

    def _delete_item(self, item_id: str) -> None:
        if not self._key:
            return
        try:
            self.store.delete_item(self._key, item_id)
        except OSError:
            pass
        if self._editing == item_id:
            self._editing = None
        self._reload()

    def _add_item(self) -> None:
        if not self._key:
            return
        try:
            item = self.store.add_item(self._key, "")
        except OSError:
            return
        self._editing = item["id"]
        self._reload()

    def _on_rows_configure(self, _event: tk.Event) -> None:
        self.canvas.configure(scrollregion=self.canvas.bbox("all") or (0, 0, 0, 0))

    def _on_canvas_configure(self, event: tk.Event) -> None:
        self.canvas.itemconfigure(self._rows_window, width=event.width)

    def _on_mousewheel(self, event: tk.Event) -> None:
        if not self.expanded:
            return
        self.canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
