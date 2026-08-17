"""Colour constants, named themes, and small theme helpers."""

from __future__ import annotations

from dataclasses import dataclass

DEFAULT_BACKGROUND = "#16181d"
DEFAULT_LIST_BACKGROUND = "#101218"
DEFAULT_TEXT = "#f4f1ea"
DEFAULT_BORDER = "#8a8175"
DEFAULT_CORNER_RADIUS = 12
MIN_CORNER_RADIUS = 0
MAX_CORNER_RADIUS = 20
RADIUS_CHOICES = (0, 8, 12, 16, 20)
TRANSPARENT = "transparent"
TRANSPARENT_KEY = "#010203"

COLOUR_PALETTE = (
    "#101218",
    "#16181d",
    "#1e293b",
    "#334155",
    "#94a3b8",
    "#f8fafc",
    "#f3ead9",
    "#e8dcc4",
    "#facc15",
    "#f97316",
    "#ef4444",
    "#ec4899",
    "#8b5cf6",
    "#2563eb",
    "#0ea5e9",
    "#059669",
)


@dataclass(frozen=True)
class ColourTheme:
    """A named preset that paints badge, list, type, and border together."""

    id: str
    name: str
    background: str
    list_background: str
    text: str
    border: str


COLOUR_THEMES = (
    ColourTheme("ink", "Ink", "#16181d", "#101218", "#f4f1ea", "#8a8175"),
    ColourTheme("slate", "Slate", "#1e293b", "#0f172a", "#f1f5f9", "#7b93b0"),
    ColourTheme("parchment", "Parchment", "#f3ead9", "#e8dcc4", "#3d2f1f", "#b89b72"),
    ColourTheme("matcha", "Matcha", "#1a2a1f", "#121c16", "#e7f0e4", "#6e9a74"),
    ColourTheme("ocean", "Ocean", "#0e1c2a", "#0a141e", "#dceefe", "#4f8fb8"),
    ColourTheme("dusk", "Dusk", "#2a1824", "#1c1018", "#fde8f0", "#c47a9a"),
)


def is_hex_color(value: object) -> bool:
    text = str(value or "").strip()
    return len(text) == 7 and text.startswith("#")


def is_transparent(color: object) -> bool:
    """Return whether a stored fill is the transparent swatch."""
    value = str(color or "").strip().lower()
    return value in {TRANSPARENT, TRANSPARENT_KEY.lower()}


def paint_color(color: object, fallback: str = DEFAULT_BACKGROUND) -> str:
    """Return a Tk fill: the colour-key for transparent, otherwise a hex."""
    if is_transparent(color):
        return TRANSPARENT_KEY
    text = str(color or "").strip()
    if is_hex_color(text):
        return text
    return fallback


def blend_hex(background: str, foreground: str, amount: float) -> str:
    """Blend two ``#RRGGBB`` colours.

    ``amount`` is the foreground proportion and must be between zero and one.
    """
    if not 0 <= amount <= 1:
        raise ValueError("amount must be between 0 and 1")
    background_rgb = tuple(int(background[i : i + 2], 16) for i in (1, 3, 5))
    foreground_rgb = tuple(int(foreground[i : i + 2], 16) for i in (1, 3, 5))
    mixed = tuple(
        round(bg + (fg - bg) * amount)
        for bg, fg in zip(background_rgb, foreground_rgb)
    )
    return "#" + "".join(f"{channel:02x}" for channel in mixed)


def bounded_int(value: object, default: int, minimum: int, maximum: int) -> int:
    """Coerce a value to an integer and clamp it to a closed interval."""
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    return max(minimum, min(maximum, parsed))


def matching_theme_id(
    background: str,
    list_background: str,
    text: str,
    border: str,
) -> str | None:
    """Return the preset id if the four fills match a theme exactly."""
    bg = str(background or "").strip().lower()
    listed = str(list_background or "").strip().lower()
    ink = str(text or "").strip().lower()
    edge = str(border or "").strip().lower()
    for theme in COLOUR_THEMES:
        if (
            theme.background.lower() == bg
            and theme.list_background.lower() == listed
            and theme.text.lower() == ink
            and theme.border.lower() == edge
        ):
            return theme.id
    return None


def theme_by_id(theme_id: str) -> ColourTheme | None:
    wanted = str(theme_id or "").strip().lower()
    for theme in COLOUR_THEMES:
        if theme.id == wanted:
            return theme
    return None
