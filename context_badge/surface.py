"""Turn a native window title into a page/surface label."""

from __future__ import annotations

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
    "obsidian.exe": (" - Obsidian",),
    "notepad.exe": (" - Notepad",),
}


def surface_label(executable: str, title: str) -> str:
    """Return the page or document name shown in a window title.

    Browser and editor titles usually append the application name. Stripping
    that suffix keeps tab/page stats grouped separately from the host app.
    """
    cleaned = title.strip() or "Untitled window"
    lower = executable.lower()
    for suffix in BROWSER_SUFFIXES.get(lower, ()) + EDITOR_SUFFIXES.get(lower, ()):
        if cleaned.endswith(suffix) and len(cleaned) > len(suffix):
            cleaned = cleaned[: -len(suffix)].rstrip(" -—–")
            break
    # Edge and some Chrome profiles insert an extra " - Profile N" tail.
    if lower in BROWSER_SUFFIXES and " - " in cleaned:
        head, tail = cleaned.rsplit(" - ", 1)
        if tail.lower().startswith("profile"):
            cleaned = head.strip()
    return cleaned or title.strip() or "Untitled window"
