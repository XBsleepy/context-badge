"""Turn a native window title (and optional UI Automation hints) into labels."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from urllib.parse import urlparse

from .uia import UiaSnapshot

BROWSER_SUFFIXES = {
    "chrome.exe": (" - Google Chrome", " - Chromium"),
    "msedge.exe": (" - Microsoft Edge", " - Microsoft Edge Dev"),
    "firefox.exe": (" - Mozilla Firefox", " - Firefox"),
    "brave.exe": (" - Brave",),
    "opera.exe": (" - Opera",),
    "vivaldi.exe": (" - Vivaldi",),
}

EDITOR_SUFFIXES = {
    "code.exe": (" - Visual Studio Code", " - VSCodium"),
    "cursor.exe": (" - Cursor",),
    "obsidian.exe": (" - Obsidian",),
    "notepad.exe": (" - Notepad",),
}

EXPLORER_SUFFIXES = (
    " - File Explorer",
    " - 文件资源管理器",
    " - Windows 资源管理器",
)

AGENTS_TITLES = {"cursor agents"}

_OTHER_PAGES = re.compile(
    r"(?:\s+和另外\s*\d+\s*个页面|\s+and\s+\d+\s+other\s+pages?)\s*$",
    re.IGNORECASE,
)
_BROWSER_TAIL = re.compile(
    r"\s+-\s+(?:Google Chrome|Chromium|Microsoft Edge(?: Dev)?|"
    r"Mozilla Firefox|Firefox|Brave|Opera|Vivaldi)\s*$",
    re.IGNORECASE,
)
_PROFILE_TAIL = re.compile(
    r"\s+-\s+(?:Profile\s+\d+|个人|工作|Work|InPrivate|Guest)\s*$",
    re.IGNORECASE,
)
_NOTIFY_PREFIX = re.compile(
    r"^\([^)]*(?:私信|消息|notification|messages?|mail)[^)]*\)\s*",
    re.IGNORECASE,
)
_MEMORY_TAIL = re.compile(
    r"(?:\s+-\s+睡眠)?\s+-\s+(?:内存使用率|Memory usage)\s+-\s+\d+\s*MB\s*$",
    re.IGNORECASE,
)
_SLEEP_TAIL = re.compile(r"\s+-\s+睡眠\s*$")
_CHAT_TITLE_PREFIX = re.compile(r"^Chat title\.\s*", re.IGNORECASE)
_EDITOR_DIRTY = re.compile(r"^[●•○]\s+")
_EDITOR_FILE_STATUS = re.compile(
    r"\s+\((?:Working Tree|Untracked|Index|Staged|Modified)\)\s*$",
    re.IGNORECASE,
)
_EDITOR_SPLIT = re.compile(r"\s+[-—–]\s+")


@dataclass(frozen=True)
class ResolvedContext:
    """Display, dwell, and todo labels for the current foreground surface."""

    display: str
    dwell_surface: str
    list_surface: str
    list_label: str


def strip_invisibles(text: str) -> str:
    """Drop format/control characters that browsers inject into titles."""
    return "".join(
        char
        for char in text
        if unicodedata.category(char) not in {"Cf", "Cc", "Cs"}
    )


def compact_url(url: str) -> str:
    """Return host+path for http(s) URLs; ignore app-internal schemes."""
    parsed = urlparse((url or "").strip())
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return ""
    path = parsed.path.rstrip("/") or ""
    return parsed.netloc + path


def editor_parts(executable: str, cleaned: str) -> tuple[str, str] | None:
    """Split `file - workspace` after the application suffix is gone."""
    if executable.lower() not in EDITOR_SUFFIXES:
        return None
    text = _EDITOR_DIRTY.sub("", (cleaned or "").strip())
    parts = [part.strip() for part in _EDITOR_SPLIT.split(text) if part.strip()]
    if len(parts) < 2:
        return None
    workspace = parts[-1]
    file_name = _EDITOR_FILE_STATUS.sub("", parts[-2]).strip()
    if not file_name or not workspace:
        return None
    return file_name, workspace


def surface_label(executable: str, title: str) -> str:
    """Return the page or document name shown in a window title.

    Browser and editor titles usually append the application name. Stripping
    that suffix keeps tab/page stats grouped separately from the host app.
    """
    cleaned = _clean_title(executable, title)
    return cleaned or title.strip() or "Untitled window"


def resolve_context(
    executable: str,
    title: str,
    snapshot: UiaSnapshot | None = None,
) -> ResolvedContext:
    """Build badge, dwell, and todo labels from the title plus UIA hints."""
    cleaned = surface_label(executable, title)
    snap = snapshot or UiaSnapshot()
    lower = executable.lower()
    chat = _chat_title(snap)
    tab = _tab_label(snap)
    file_tab = _file_tab(snap)
    url_key = compact_url(snap.url)

    if chat and cleaned.lower() in AGENTS_TITLES:
        return ResolvedContext(chat, chat, chat, chat)

    if lower in BROWSER_SUFFIXES:
        display = tab or cleaned
        listed = url_key or display
        return ResolvedContext(display, display, listed, display)

    parts = editor_parts(lower, cleaned)
    if parts is not None:
        file_name, workspace = parts
        if file_tab:
            file_name = file_tab
        display = f"{file_name} · {workspace}"
        return ResolvedContext(
            display,
            f"{file_name} - {workspace}",
            workspace,
            workspace,
        )

    if chat:
        return ResolvedContext(chat, chat, chat, chat)

    return ResolvedContext(cleaned, cleaned, cleaned, cleaned)


def _clean_title(executable: str, title: str) -> str:
    cleaned = strip_invisibles(title).strip() or "Untitled window"
    lower = executable.lower()
    cleaned = _MEMORY_TAIL.sub("", cleaned).strip()
    cleaned = _SLEEP_TAIL.sub("", cleaned).strip()
    if lower in BROWSER_SUFFIXES:
        cleaned = _BROWSER_TAIL.sub("", cleaned).strip()
        cleaned = _PROFILE_TAIL.sub("", cleaned).strip()
        cleaned = _OTHER_PAGES.sub("", cleaned).strip()
        cleaned = _BROWSER_TAIL.sub("", cleaned).strip()
        cleaned = _NOTIFY_PREFIX.sub("", cleaned).strip()
        cleaned = _MEMORY_TAIL.sub("", cleaned).strip()
    else:
        for suffix in BROWSER_SUFFIXES.get(lower, ()) + EDITOR_SUFFIXES.get(
            lower, ()
        ):
            if cleaned.endswith(suffix) and len(cleaned) > len(suffix):
                cleaned = cleaned[: -len(suffix)].rstrip(" -—–")
                break
        if lower in EDITOR_SUFFIXES:
            cleaned = _EDITOR_DIRTY.sub("", cleaned).strip()
        if lower == "explorer.exe":
            for suffix in EXPLORER_SUFFIXES:
                if cleaned.endswith(suffix) and len(cleaned) > len(suffix):
                    cleaned = cleaned[: -len(suffix)].rstrip(" -—–")
                    break
    return cleaned or title.strip() or "Untitled window"


def _tab_label(snapshot: UiaSnapshot) -> str:
    name = strip_invisibles(snapshot.tab_name).strip()
    name = _MEMORY_TAIL.sub("", name).strip()
    name = _SLEEP_TAIL.sub("", name).strip()
    name = _NOTIFY_PREFIX.sub("", name).strip()
    return name


def _file_tab(snapshot: UiaSnapshot) -> str:
    name = strip_invisibles(snapshot.file_tab).strip()
    if not name:
        return ""
    return name.split(",", 1)[0].strip()


def _chat_title(snapshot: UiaSnapshot) -> str:
    name = strip_invisibles(snapshot.chat_title).strip()
    if not name:
        return ""
    return _CHAT_TITLE_PREFIX.sub("", name).strip()
