"""Topmost per-pixel-alpha pet window driven by PetMachine."""

from __future__ import annotations

import ctypes
from ctypes import POINTER, byref, c_void_p, sizeof
from ctypes.wintypes import DWORD, HBITMAP, HDC, HINSTANCE, HWND, LONG, LPARAM, UINT, WORD, WPARAM
from collections.abc import Callable
from pathlib import Path

import tkinter as tk

from .pet_atlas import PetAtlas, load_pet_atlas
from .pet_machine import PetMachine
from .pet_place import (
    BadgeAnchor,
    PetSize,
    normalize_placement,
    normalize_scale_percent,
    place_pet,
)
from .pet_spec import IDLE, CellRef
from .win32 import (
    GWL_EXSTYLE,
    HWND_TOPMOST,
    SWP_FRAMECHANGED,
    SWP_NOACTIVATE,
    SWP_NOMOVE,
    SWP_NOSIZE,
    SW_HIDE,
    SW_SHOWNOACTIVATE,
    WS_EX_LAYERED,
    WS_EX_NOACTIVATE,
    WS_EX_TOOLWINDOW,
    set_window_owner,
    monitor_work_area,
    user32,
)

ULW_ALPHA = 0x00000002
AC_SRC_OVER = 0x00
AC_SRC_ALPHA = 0x01
BI_RGB = 0
DIB_RGB_COLORS = 0
GWLP_HWNDPARENT = -8
WS_POPUP = 0x80000000
WS_EX_TOPMOST = 0x00000008
WM_NCHITTEST = 0x0084
WM_PAINT = 0x000F
WM_ERASEBKGND = 0x0014
WM_NCPAINT = 0x0085
WM_SETCURSOR = 0x0020
WM_MOUSEMOVE = 0x0200
WM_LBUTTONDOWN = 0x0201
WM_LBUTTONUP = 0x0202
WM_CAPTURECHANGED = 0x0215
HTCLIENT = 1
HTTRANSPARENT = -1
SWP_NOREDRAW = 0x0008
ERROR_CLASS_ALREADY_EXISTS = 1410
IDC_SIZENWSE = 32642
IDC_SIZEALL = 32646
ALPHA_HIT_MIN = 24

gdi32 = ctypes.WinDLL("gdi32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
LRESULT = ctypes.c_ssize_t
WNDPROC = ctypes.WINFUNCTYPE(LRESULT, HWND, UINT, WPARAM, LPARAM)


class POINT(ctypes.Structure):
    _fields_ = [("x", LONG), ("y", LONG)]


class SIZE(ctypes.Structure):
    _fields_ = [("cx", LONG), ("cy", LONG)]


class BLENDFUNCTION(ctypes.Structure):
    _pack_ = 1
    _fields_ = [
        ("BlendOp", ctypes.c_byte),
        ("BlendFlags", ctypes.c_byte),
        ("SourceConstantAlpha", ctypes.c_byte),
        ("AlphaFormat", ctypes.c_byte),
    ]


class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [
        ("biSize", DWORD),
        ("biWidth", LONG),
        ("biHeight", LONG),
        ("biPlanes", WORD),
        ("biBitCount", WORD),
        ("biCompression", DWORD),
        ("biSizeImage", DWORD),
        ("biXPelsPerMeter", LONG),
        ("biYPelsPerMeter", LONG),
        ("biClrUsed", DWORD),
        ("biClrImportant", DWORD),
    ]


class BITMAPINFO(ctypes.Structure):
    _fields_ = [("bmiHeader", BITMAPINFOHEADER), ("bmiColors", DWORD * 3)]


class WNDCLASSEXW(ctypes.Structure):
    _fields_ = [
        ("cbSize", UINT),
        ("style", UINT),
        ("lpfnWndProc", WNDPROC),
        ("cbClsExtra", ctypes.c_int),
        ("cbWndExtra", ctypes.c_int),
        ("hInstance", HINSTANCE),
        ("hIcon", ctypes.c_void_p),
        ("hCursor", ctypes.c_void_p),
        ("hbrBackground", ctypes.c_void_p),
        ("lpszMenuName", ctypes.c_wchar_p),
        ("lpszClassName", ctypes.c_wchar_p),
        ("hIconSm", ctypes.c_void_p),
    ]


gdi32.CreateCompatibleDC.argtypes = [HDC]
gdi32.CreateCompatibleDC.restype = HDC
gdi32.CreateDIBSection.argtypes = [
    HDC,
    POINTER(BITMAPINFO),
    DWORD,
    POINTER(c_void_p),
    ctypes.c_void_p,
    DWORD,
]
gdi32.CreateDIBSection.restype = HBITMAP
gdi32.SelectObject.argtypes = [HDC, ctypes.c_void_p]
gdi32.SelectObject.restype = ctypes.c_void_p
gdi32.DeleteObject.argtypes = [ctypes.c_void_p]
gdi32.DeleteDC.argtypes = [HDC]
user32.UpdateLayeredWindow.argtypes = [
    HWND,
    HDC,
    POINTER(POINT),
    POINTER(SIZE),
    HDC,
    POINTER(POINT),
    DWORD,
    POINTER(BLENDFUNCTION),
    DWORD,
]
user32.UpdateLayeredWindow.restype = ctypes.c_int
user32.DefWindowProcW.argtypes = [HWND, UINT, WPARAM, LPARAM]
user32.DefWindowProcW.restype = LRESULT
user32.RegisterClassExW.argtypes = [POINTER(WNDCLASSEXW)]
user32.RegisterClassExW.restype = ctypes.c_ushort
user32.CreateWindowExW.argtypes = [
    DWORD,
    ctypes.c_wchar_p,
    ctypes.c_wchar_p,
    DWORD,
    ctypes.c_int,
    ctypes.c_int,
    ctypes.c_int,
    ctypes.c_int,
    HWND,
    ctypes.c_void_p,
    HINSTANCE,
    ctypes.c_void_p,
]
user32.CreateWindowExW.restype = HWND
user32.DestroyWindow.argtypes = [HWND]
kernel32.GetModuleHandleW.argtypes = [ctypes.c_wchar_p]
kernel32.GetModuleHandleW.restype = HINSTANCE
user32.ShowWindow.argtypes = [HWND, ctypes.c_int]
user32.IsWindowVisible.argtypes = [HWND]
user32.IsWindowVisible.restype = ctypes.c_int
user32.GetCursorPos.argtypes = [POINTER(POINT)]
user32.GetCursorPos.restype = ctypes.c_int
user32.SetCapture.argtypes = [HWND]
user32.SetCapture.restype = HWND
user32.ReleaseCapture.argtypes = []
user32.ReleaseCapture.restype = ctypes.c_int
user32.GetCapture.argtypes = []
user32.GetCapture.restype = HWND
user32.LoadCursorW.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
user32.LoadCursorW.restype = ctypes.c_void_p
user32.SetCursor.argtypes = [ctypes.c_void_p]
user32.SetCursor.restype = ctypes.c_void_p

_PET_WINDOWS: dict[int, "PetOverlay"] = {}
_POINTER_PUMP_MS = 16


def _pet_wndproc(hwnd: int, msg: int, wparam: int, lparam: int) -> int:
    # Keep this callback off the Tk event loop. Calling geometry() / after()
    # from here re-enters Tcl while ctypes still owns the GIL and crashes
    # with PyEval_RestoreThread.
    overlay = _PET_WINDOWS.get(int(hwnd))
    if overlay is None:
        return int(user32.DefWindowProcW(hwnd, msg, wparam, lparam))
    nested = overlay._in_native > 0
    overlay._in_native += 1
    try:
        try:
            result = overlay._native_message(int(msg), int(wparam), int(lparam))
        except Exception:
            return 0
        if result is not None:
            return int(result)
        if nested:
            return 0
        return int(user32.DefWindowProcW(hwnd, msg, wparam, lparam))
    finally:
        overlay._in_native -= 1


_PET_WNDPROC = WNDPROC(_pet_wndproc)
_PET_CLASS = "ContextBadgePet"
_pet_class_registered = False


def _register_pet_class() -> None:
    global _pet_class_registered
    if _pet_class_registered:
        return
    cls = WNDCLASSEXW()
    cls.cbSize = sizeof(WNDCLASSEXW)
    cls.lpfnWndProc = _PET_WNDPROC
    cls.hInstance = kernel32.GetModuleHandleW(None)
    cls.lpszClassName = _PET_CLASS
    atom = user32.RegisterClassExW(byref(cls))
    if not atom:
        err = ctypes.get_last_error()
        if err != ERROR_CLASS_ALREADY_EXISTS:
            raise OSError(f"RegisterClassExW failed: {err}")
    _pet_class_registered = True


def _create_pet_hwnd() -> int:
    _register_pet_class()
    hwnd = user32.CreateWindowExW(
        WS_EX_LAYERED | WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE | WS_EX_TOPMOST,
        _PET_CLASS,
        "Context Badge pet",
        WS_POPUP,
        0,
        0,
        1,
        1,
        None,
        None,
        kernel32.GetModuleHandleW(None),
        None,
    )
    if not hwnd:
        raise OSError(f"CreateWindowExW failed: {ctypes.get_last_error()}")
    return int(hwnd)


class LayeredBitmap:
    """A reusable 32-bit DIB used as the UpdateLayeredWindow source."""

    def __init__(self, width: int, height: int) -> None:
        self.width = int(width)
        self.height = int(height)
        self.hdc = gdi32.CreateCompatibleDC(None)
        info = BITMAPINFO()
        info.bmiHeader.biSize = sizeof(BITMAPINFOHEADER)
        info.bmiHeader.biWidth = self.width
        info.bmiHeader.biHeight = -self.height
        info.bmiHeader.biPlanes = 1
        info.bmiHeader.biBitCount = 32
        info.bmiHeader.biCompression = BI_RGB
        bits = c_void_p()
        self.hbmp = gdi32.CreateDIBSection(
            self.hdc, byref(info), DIB_RGB_COLORS, byref(bits), None, 0
        )
        if not self.hdc or not self.hbmp or not bits:
            self.close()
            raise OSError("could not create layered bitmap")
        self.bits = bits
        self._old = gdi32.SelectObject(self.hdc, self.hbmp)

    def copy_pixels(self, bgra: bytes) -> None:
        expected = self.width * self.height * 4
        if len(bgra) != expected:
            raise ValueError("frame size does not match layered bitmap")
        ctypes.memmove(self.bits, bgra, expected)

    def alpha_at(self, x: int, y: int) -> int:
        if self.bits is None or not self.bits.value:
            return 0
        if x < 0 or y < 0 or x >= self.width or y >= self.height:
            return 0
        addr = int(self.bits.value) + (y * self.width + x) * 4 + 3
        return int(ctypes.c_ubyte.from_address(addr).value)

    def close(self) -> None:
        if getattr(self, "_old", None) and self.hdc:
            gdi32.SelectObject(self.hdc, self._old)
            self._old = None
        if getattr(self, "hbmp", None):
            gdi32.DeleteObject(self.hbmp)
            self.hbmp = None
        if getattr(self, "hdc", None):
            gdi32.DeleteDC(self.hdc)
            self.hdc = None


class PetOverlay:
    """A companion sprite that follows the badge and can be dragged."""

    def __init__(
        self,
        parent: tk.Misc,
        *,
        on_pointer: Callable[[str, int, int], None] | None = None,
    ) -> None:
        self._tk = parent
        self._on_pointer = on_pointer
        self.machine = PetMachine()
        self.atlas: PetAtlas | None = None
        self.placement = "perch_top"
        self.enabled = False
        self._click_through = False
        self._pointer_mode = "move"
        self._dragging = False
        self._in_native = 0
        self._pointer_events: list[tuple[str, int, int]] = []
        self._pointer_job: str | None = None
        self._hidden = True
        self._x = 0
        self._y = 0
        self._job: str | None = None
        self._shown: CellRef | None = None
        self._bitmap: LayeredBitmap | None = None
        self.hwnd = _create_pet_hwnd()
        _PET_WINDOWS[self.hwnd] = self
        self._apply_window_style()

    def _apply_window_style(self) -> None:
        style = user32.GetWindowLongW(self.hwnd, GWL_EXSTYLE)
        user32.SetWindowLongW(self.hwnd, GWL_EXSTYLE, style & ~WS_EX_LAYERED)
        style = user32.GetWindowLongW(self.hwnd, GWL_EXSTYLE)
        style |= (
            WS_EX_LAYERED
            | WS_EX_TOOLWINDOW
            | WS_EX_NOACTIVATE
            | WS_EX_TOPMOST
        )
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

    def set_owner(self, owner_hwnd: int) -> None:
        set_window_owner(self.hwnd, GWLP_HWNDPARENT, int(owner_hwnd or 0))

    def load(self, folder: Path, *, scale: float = 0.5) -> bool:
        try:
            atlas = load_pet_atlas(folder, scale=scale)
        except (OSError, ValueError, FileNotFoundError, TypeError):
            self.unload()
            return False
        self.atlas = atlas
        self._rebuild_bitmap()
        self.machine.request(IDLE)
        self._shown = None
        return True

    def unload(self) -> None:
        self.hide()
        self.atlas = None
        self._shown = None
        if self._bitmap is not None:
            self._bitmap.close()
            self._bitmap = None

    def set_placement(self, placement: str) -> None:
        self.placement = normalize_placement(placement)

    def set_click_through(self, enabled: bool) -> None:
        self._click_through = bool(enabled)

    def set_pointer_mode(self, mode: str) -> None:
        name = str(mode or "move").strip()
        self._pointer_mode = name if name in {"move", "place", "size"} else "move"

    def set_scale_percent(self, percent: int) -> None:
        scale = normalize_scale_percent(percent) / 100.0
        if self.atlas is None:
            return
        width = self.atlas.cell_width
        height = self.atlas.cell_height
        self.atlas.set_scale(scale)
        if self.atlas.cell_width == width and self.atlas.cell_height == height:
            return
        self._rebuild_bitmap()
        self._shown = None

    def set_enabled(self, enabled: bool) -> None:
        self.enabled = bool(enabled)
        if not self.enabled:
            self.hide()

    def follow(
        self,
        badge_x: int,
        badge_y: int,
        badge_width: int,
        badge_height: int,
        *,
        body_width: int = 0,
        offset: tuple[int, int] | None = None,
    ) -> None:
        if not self.enabled or self.atlas is None:
            self.hide()
            return
        if offset is None:
            x, y = place_pet(
                self.placement,
                BadgeAnchor(
                    badge_x,
                    badge_y,
                    badge_width,
                    badge_height,
                    body_width=body_width,
                ),
                PetSize(self.atlas.cell_width, self.atlas.cell_height),
            )
        else:
            x = int(badge_x) + int(offset[0])
            y = int(badge_y) + int(offset[1])
        work = monitor_work_area(self.hwnd)
        x = max(work.left, min(int(x), work.right - self.atlas.cell_width))
        y = max(work.top, min(int(y), work.bottom - self.atlas.cell_height))
        same_spot = x == self._x and y == self._y
        self._x = int(x)
        self._y = int(y)
        was_hidden = self._hidden
        self._hidden = False
        if self._shown is None:
            self._present(self.machine.current_cell(), force=True)
        elif was_hidden or not same_spot:
            self._move_only()
        self._kick()
        self._arm_pointer_pump()

    def show(self) -> None:
        if not self.enabled or self.atlas is None:
            return
        self._hidden = False
        if self._shown is None:
            self._present(self.machine.current_cell(), force=True)
        else:
            self._move_only()
        self._arm_pointer_pump()

    @property
    def origin(self) -> tuple[int, int]:
        return int(self._x), int(self._y)

    @property
    def size(self) -> tuple[int, int]:
        if self.atlas is None:
            return 0, 0
        return int(self.atlas.cell_width), int(self.atlas.cell_height)

    def hide(self) -> None:
        self._hidden = True
        self.stop()
        if self.hwnd:
            user32.ShowWindow(self.hwnd, SW_HIDE)

    def raise_pet(self) -> None:
        if self._hidden or not self.enabled or not self.hwnd:
            return
        user32.SetWindowPos(
            self.hwnd,
            HWND_TOPMOST,
            0,
            0,
            0,
            0,
            SWP_NOSIZE | SWP_NOMOVE | SWP_NOACTIVATE | SWP_NOREDRAW,
        )

    def _native_message(self, msg: int, wparam: int, lparam: int) -> int | None:
        if msg == WM_NCHITTEST:
            return self._hit_test(lparam)
        if msg == WM_SETCURSOR:
            self._apply_cursor()
            return 1
        if msg == WM_LBUTTONDOWN:
            self._note_pointer("press")
            return 0
        if msg == WM_MOUSEMOVE:
            if self._dragging:
                self._note_pointer("drag")
            return 0
        if msg == WM_LBUTTONUP:
            self._note_pointer("release")
            return 0
        if msg == WM_CAPTURECHANGED:
            if self._dragging and int(wparam) != int(self.hwnd):
                self._note_pointer("release")
            return 0
        if msg == WM_ERASEBKGND:
            return 1
        if msg in (WM_PAINT, WM_NCPAINT):
            return 0
        return None

    def _hit_test(self, lparam: int) -> int:
        if self._click_through or not self.enabled or self._hidden:
            return HTTRANSPARENT
        screen_x = ctypes.c_short(lparam & 0xFFFF).value
        screen_y = ctypes.c_short((lparam >> 16) & 0xFFFF).value
        local_x = int(screen_x) - self._x
        local_y = int(screen_y) - self._y
        if self._bitmap is None or self._bitmap.alpha_at(local_x, local_y) < ALPHA_HIT_MIN:
            return HTTRANSPARENT
        return HTCLIENT

    def _apply_cursor(self) -> None:
        cursor_id = IDC_SIZENWSE if self._pointer_mode == "size" else IDC_SIZEALL
        handle = user32.LoadCursorW(None, ctypes.c_void_p(cursor_id))
        if handle:
            user32.SetCursor(handle)

    def _cursor_pos(self) -> tuple[int, int]:
        point = POINT()
        if not user32.GetCursorPos(byref(point)):
            return self._x, self._y
        return int(point.x), int(point.y)

    def _note_pointer(self, phase: str) -> None:
        x, y = self._cursor_pos()
        if phase == "press":
            user32.SetCapture(self.hwnd)
            self._dragging = True
            self._pointer_events.append(("press", x, y))
            return
        if phase == "drag":
            if not self._dragging:
                return
            if self._pointer_events and self._pointer_events[-1][0] == "drag":
                self._pointer_events[-1] = ("drag", x, y)
            else:
                self._pointer_events.append(("drag", x, y))
            return
        if not self._dragging:
            return
        self._dragging = False
        if int(user32.GetCapture() or 0) == int(self.hwnd):
            user32.ReleaseCapture()
        self._pointer_events.append(("release", x, y))

    def _arm_pointer_pump(self) -> None:
        if self._pointer_job is not None or self._hidden:
            return
        try:
            self._pointer_job = self._tk.after(_POINTER_PUMP_MS, self._pump_pointer)
        except tk.TclError:
            self._pointer_job = None

    def _pump_pointer(self) -> None:
        self._pointer_job = None
        events = self._pointer_events
        self._pointer_events = []
        callback = self._on_pointer
        if callback is not None:
            for phase, x, y in events:
                try:
                    callback(phase, x, y)
                except tk.TclError:
                    break
        if not self._hidden:
            self._arm_pointer_pump()

    def stop(self) -> None:
        if self._job is not None:
            try:
                self._tk.after_cancel(self._job)
            except tk.TclError:
                pass
            self._job = None
        if self._pointer_job is not None:
            try:
                self._tk.after_cancel(self._pointer_job)
            except tk.TclError:
                pass
            self._pointer_job = None

    def _kick(self) -> None:
        if self._job is not None or self._hidden:
            return
        delay = self.machine.current_delay_ms()
        try:
            self._job = self._tk.after(delay, self._on_frame)
        except tk.TclError:
            self._job = None

    def _on_frame(self) -> None:
        self._job = None
        if self._hidden or self.atlas is None:
            return
        self.machine.advance()
        self._present(self.machine.current_cell())
        self._kick()

    def _present(self, cell: CellRef | None = None, *, force: bool = False) -> None:
        if self.atlas is None or self._bitmap is None:
            return
        if cell is None:
            cell = self.machine.current_cell()
        if not force and cell == self._shown:
            self._move_only()
            return
        try:
            self._bitmap.copy_pixels(self.atlas.frame(cell))
        except (OSError, ValueError):
            return
        self._shown = cell
        self._update_layered()

    def _move_only(self) -> None:
        if self._bitmap is None:
            return
        self._update_layered()

    def _update_layered(self) -> None:
        if self._bitmap is None or not self.hwnd:
            return
        if not self._blit():
            self._apply_window_style()
            self._blit()

    def _blit(self) -> bool:
        if self._bitmap is None:
            return False
        dst = POINT(self._x, self._y)
        size = SIZE(self._bitmap.width, self._bitmap.height)
        src = POINT(0, 0)
        blend = BLENDFUNCTION(AC_SRC_OVER, 0, 255, AC_SRC_ALPHA)
        painted = bool(
            user32.UpdateLayeredWindow(
                self.hwnd,
                HDC(0),
                byref(dst),
                byref(size),
                self._bitmap.hdc,
                byref(src),
                0,
                byref(blend),
                ULW_ALPHA,
            )
        )
        if painted and not self._hidden and not user32.IsWindowVisible(self.hwnd):
            user32.ShowWindow(self.hwnd, SW_SHOWNOACTIVATE)
        return painted

    def _rebuild_bitmap(self) -> None:
        if self._bitmap is not None:
            self._bitmap.close()
            self._bitmap = None
        if self.atlas is None:
            return
        self._bitmap = LayeredBitmap(self.atlas.cell_width, self.atlas.cell_height)
