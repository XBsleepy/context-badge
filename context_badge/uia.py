"""Read selected tab, URL, and chat title via the UI Automation C API.

``CUIAutomation`` COM is not always registered, so this uses
``UIAutomationCore.dll`` (``UiaNodeFromHandle`` / ``UiaFind``) on a dedicated
STA thread. Queries time out and fall back to window-title cleaning.
"""

from __future__ import annotations

import ctypes
import queue
import threading
from ctypes import wintypes
from dataclasses import dataclass

ole32 = ctypes.WinDLL("ole32")
oleaut32 = ctypes.WinDLL("oleaut32")
uia_core = ctypes.WinDLL("UIAutomationCore.dll")

COINIT_APARTMENTTHREADED = 0x2
S_OK = 0
VT_I4 = 3
VT_BSTR = 8
VT_BOOL = 11
VT_I8 = 20

UIA_CONTROL_TYPE_PROPERTY_ID = 30003
UIA_NAME_PROPERTY_ID = 30005
UIA_CLASS_NAME_PROPERTY_ID = 30012
UIA_VALUE_VALUE_PROPERTY_ID = 30045
UIA_IS_SELECTED_PROPERTY_ID = 30079

UIA_BUTTON_CONTROL_TYPE = 50000
UIA_EDIT_CONTROL_TYPE = 50004
UIA_TAB_ITEM_CONTROL_TYPE = 50019

TREE_SCOPE_ELEMENT = 0x1
VARIANT_TRUE = -1
CONDITION_TYPE_TRUE = 0
CONDITION_TYPE_PROPERTY = 2

_INSPECT_TIMEOUT = 0.45
_CHAT_TITLE_PREFIX = "chat title."


@dataclass(frozen=True)
class UiaSnapshot:
    """Optional accessibility hints for the foreground window."""

    tab_name: str = ""
    url: str = ""
    chat_title: str = ""
    file_tab: str = ""


class VARIANT(ctypes.Structure):
    class _UNION(ctypes.Union):
        _fields_ = [
            ("llVal", ctypes.c_longlong),
            ("lVal", ctypes.c_int),
            ("bstrVal", ctypes.c_void_p),
            ("boolVal", ctypes.c_short),
            ("blob", ctypes.c_byte * 16),
        ]

    _anonymous_ = ("u",)
    _fields_ = [
        ("vt", ctypes.c_ushort),
        ("wReserved1", ctypes.c_ushort),
        ("wReserved2", ctypes.c_ushort),
        ("wReserved3", ctypes.c_ushort),
        ("u", _UNION),
    ]


class UiaCondition(ctypes.Structure):
    _fields_ = [("ConditionType", ctypes.c_int)]


class UiaPropertyCondition(ctypes.Structure):
    _pack_ = 8
    _fields_ = [
        ("ConditionType", ctypes.c_int),
        ("PropertyId", ctypes.c_int),
        ("Value", VARIANT),
        ("Flags", ctypes.c_int),
    ]


class UiaFindParams(ctypes.Structure):
    _fields_ = [
        ("MaxDepth", ctypes.c_int),
        ("FindFirst", ctypes.c_int),
        ("ExcludeRoot", ctypes.c_int),
        ("pFindCondition", ctypes.c_void_p),
    ]


class UiaCacheRequest(ctypes.Structure):
    _fields_ = [
        ("pViewCondition", ctypes.c_void_p),
        ("Scope", ctypes.c_int),
        ("pProperties", ctypes.POINTER(ctypes.c_int)),
        ("cProperties", ctypes.c_int),
        ("pPatterns", ctypes.POINTER(ctypes.c_int)),
        ("cPatterns", ctypes.c_int),
        ("automationElementMode", ctypes.c_int),
    ]


class SAFEARRAYBOUND(ctypes.Structure):
    _fields_ = [("cElements", ctypes.c_uint), ("lLbound", ctypes.c_long)]


class SAFEARRAY(ctypes.Structure):
    _fields_ = [
        ("cDims", ctypes.c_ushort),
        ("fFeatures", ctypes.c_ushort),
        ("cbElements", ctypes.c_uint),
        ("cLocks", ctypes.c_uint),
        ("pvData", ctypes.c_void_p),
        ("rgsabound", SAFEARRAYBOUND * 2),
    ]


ole32.CoInitializeEx.argtypes = [ctypes.c_void_p, ctypes.c_uint]
ole32.CoInitializeEx.restype = ctypes.c_long
oleaut32.VariantInit.argtypes = [ctypes.POINTER(VARIANT)]
oleaut32.VariantClear.argtypes = [ctypes.POINTER(VARIANT)]
oleaut32.SafeArrayDestroy.argtypes = [ctypes.c_void_p]
oleaut32.SafeArrayDestroy.restype = ctypes.c_long

uia_core.UiaNodeFromHandle.restype = ctypes.c_long
uia_core.UiaNodeFromHandle.argtypes = [
    wintypes.HWND,
    ctypes.POINTER(ctypes.c_void_p),
]
uia_core.UiaGetPropertyValue.restype = ctypes.c_long
uia_core.UiaGetPropertyValue.argtypes = [
    ctypes.c_void_p,
    ctypes.c_int,
    ctypes.POINTER(VARIANT),
]
uia_core.UiaNodeRelease.argtypes = [ctypes.c_void_p]
uia_core.UiaNodeRelease.restype = ctypes.c_int
uia_core.UiaHUiaNodeFromVariant.restype = ctypes.c_long
uia_core.UiaHUiaNodeFromVariant.argtypes = [
    ctypes.POINTER(VARIANT),
    ctypes.POINTER(ctypes.c_void_p),
]
uia_core.UiaFind.restype = ctypes.c_long
uia_core.UiaFind.argtypes = [
    ctypes.c_void_p,
    ctypes.POINTER(UiaFindParams),
    ctypes.POINTER(UiaCacheRequest),
    ctypes.POINTER(ctypes.c_void_p),
    ctypes.POINTER(ctypes.c_void_p),
    ctypes.POINTER(ctypes.c_void_p),
]


def _property(node: int, property_id: int) -> VARIANT:
    value = VARIANT()
    oleaut32.VariantInit(ctypes.byref(value))
    hr = uia_core.UiaGetPropertyValue(node, property_id, ctypes.byref(value))
    if hr != S_OK:
        oleaut32.VariantClear(ctypes.byref(value))
        return VARIANT()
    return value


def _bstr(variant: VARIANT) -> str:
    if variant.vt != VT_BSTR or not variant.bstrVal:
        return ""
    return ctypes.wstring_at(variant.bstrVal)


def _name_of(node: int) -> str:
    value = _property(node, UIA_NAME_PROPERTY_ID)
    try:
        return _bstr(value)
    finally:
        oleaut32.VariantClear(ctypes.byref(value))


def _class_of(node: int) -> str:
    value = _property(node, UIA_CLASS_NAME_PROPERTY_ID)
    try:
        return _bstr(value)
    finally:
        oleaut32.VariantClear(ctypes.byref(value))


def _value_of(node: int) -> str:
    value = _property(node, UIA_VALUE_VALUE_PROPERTY_ID)
    try:
        return _bstr(value)
    finally:
        oleaut32.VariantClear(ctypes.byref(value))


def _is_selected(node: int) -> bool:
    value = _property(node, UIA_IS_SELECTED_PROPERTY_ID)
    try:
        return value.vt == VT_BOOL and value.boolVal == VARIANT_TRUE
    finally:
        oleaut32.VariantClear(ctypes.byref(value))


def _type_condition(control_type: int) -> UiaPropertyCondition:
    condition = UiaPropertyCondition()
    condition.ConditionType = CONDITION_TYPE_PROPERTY
    condition.PropertyId = UIA_CONTROL_TYPE_PROPERTY_ID
    condition.Value.vt = VT_I4
    condition.Value.lVal = control_type
    return condition


def _find_records(root: int, control_type: int, limit: int = 80) -> list[tuple[str, str, bool, str]]:
    view = UiaCondition(CONDITION_TYPE_TRUE)
    match = _type_condition(control_type)
    params = UiaFindParams(-1, 0, 1, ctypes.addressof(match))
    props = (ctypes.c_int * 1)(UIA_NAME_PROPERTY_ID)
    request = UiaCacheRequest()
    request.pViewCondition = ctypes.addressof(view)
    request.Scope = TREE_SCOPE_ELEMENT
    request.pProperties = ctypes.cast(props, ctypes.POINTER(ctypes.c_int))
    request.cProperties = 1
    request.pPatterns = None
    request.cPatterns = 0
    request.automationElementMode = 1
    props_sa = ctypes.c_void_p()
    offsets_sa = ctypes.c_void_p()
    tree_sa = ctypes.c_void_p()
    hr = uia_core.UiaFind(
        root,
        ctypes.byref(params),
        ctypes.byref(request),
        ctypes.byref(props_sa),
        ctypes.byref(offsets_sa),
        ctypes.byref(tree_sa),
    )
    records: list[tuple[str, str, bool, str]] = []
    if hr == S_OK and props_sa.value:
        array = ctypes.cast(props_sa.value, ctypes.POINTER(SAFEARRAY)).contents
        count = array.rgsabound[0].cElements
        if array.cDims > 1:
            count *= array.rgsabound[1].cElements
        variants = ctypes.cast(array.pvData, ctypes.POINTER(VARIANT))
        for index in range(count):
            if len(records) >= limit:
                break
            if variants[index].vt != VT_I8:
                continue
            node = int(variants[index].llVal)
            if not node:
                continue
            records.append(
                (_name_of(node), _class_of(node), _is_selected(node), _value_of(node))
            )
        oleaut32.SafeArrayDestroy(props_sa)
    if offsets_sa.value:
        oleaut32.SafeArrayDestroy(offsets_sa)
    if tree_sa.value:
        oleaut32.SafeArrayDestroy(tree_sa)
    return records


def _http_url(value: str) -> str:
    text = (value or "").strip()
    if text.startswith("http://") or text.startswith("https://"):
        return text
    return ""


def _inspect_sync(hwnd: int, *, browser: bool, agents: bool) -> UiaSnapshot:
    root_ptr = ctypes.c_void_p()
    if uia_core.UiaNodeFromHandle(hwnd, ctypes.byref(root_ptr)) != S_OK or not root_ptr.value:
        return UiaSnapshot()
    root = int(root_ptr.value)
    tab_name = ""
    file_tab = ""
    url = ""
    chat_title = ""
    try:
        if browser:
            for name, class_name, selected, _value in _find_records(
                root, UIA_TAB_ITEM_CONTROL_TYPE, 24
            ):
                if "close" in class_name.lower() or not selected:
                    continue
                if class_name.startswith("tab ") or " tab " in f" {class_name}":
                    file_tab = file_tab or name
                    continue
                if "composite-bar" in class_name:
                    continue
                tab_name = name
                break
            fallback = ""
            for name, class_name, _selected, value in _find_records(
                root, UIA_EDIT_CONTROL_TYPE, 12
            ):
                candidate = _http_url(value)
                if not candidate:
                    continue
                lowered = class_name.lower()
                if (
                    "omnibox" in lowered
                    or "地址" in name
                    or "address" in name.lower()
                    or "search" in name.lower()
                ):
                    url = candidate
                    break
                fallback = fallback or candidate
            url = url or fallback
        if agents:
            for name, class_name, _selected, _value in _find_records(
                root, UIA_BUTTON_CONTROL_TYPE, 80
            ):
                if name.lower().startswith(_CHAT_TITLE_PREFIX):
                    chat_title = name
                    break
                if "chat-title-tab-trigger" in class_name and name:
                    chat_title = name
                    break
        return UiaSnapshot(
            tab_name=tab_name,
            url=url,
            chat_title=chat_title,
            file_tab=file_tab,
        )
    finally:
        uia_core.UiaNodeRelease(root)


class _UiaWorker:
    def __init__(self) -> None:
        self._requests: queue.Queue[
            tuple[int, bool, bool, queue.Queue[UiaSnapshot | None]]
        ] = queue.Queue()
        self._thread = threading.Thread(target=self._run, name="uia-sta", daemon=True)
        self._thread.start()

    def inspect(
        self,
        hwnd: int,
        *,
        browser: bool,
        agents: bool,
        timeout: float,
    ) -> UiaSnapshot | None:
        reply: queue.Queue[UiaSnapshot | None] = queue.Queue(maxsize=1)
        self._requests.put((int(hwnd), browser, agents, reply))
        try:
            return reply.get(timeout=timeout)
        except queue.Empty:
            return None

    def _run(self) -> None:
        ole32.CoInitializeEx(None, COINIT_APARTMENTTHREADED)
        while True:
            hwnd, browser, agents, reply = self._requests.get()
            snapshot: UiaSnapshot | None
            try:
                snapshot = _inspect_sync(hwnd, browser=browser, agents=agents)
            except OSError:
                snapshot = None
            try:
                reply.put_nowait(snapshot)
            except queue.Full:
                pass


_worker: _UiaWorker | None = None
_worker_lock = threading.Lock()


def inspect_window(
    hwnd: int,
    *,
    browser: bool = False,
    agents: bool = False,
    timeout: float = _INSPECT_TIMEOUT,
) -> UiaSnapshot | None:
    """Return a snapshot for ``hwnd``, or None if UIA is slow or unavailable."""
    if not hwnd or not (browser or agents):
        return UiaSnapshot()
    global _worker
    with _worker_lock:
        if _worker is None:
            _worker = _UiaWorker()
        worker = _worker
    return worker.inspect(hwnd, browser=browser, agents=agents, timeout=timeout)
