"""Colour constants and small theme helpers."""

DEFAULT_BACKGROUND = "#263244"
DEFAULT_TEXT = "#f4f7fb"
TRANSPARENT_KEY = "#010203"

COLOUR_PALETTE = (
    "#0f172a",
    "#263244",
    "#475569",
    "#94a3b8",
    "#f8fafc",
    "#facc15",
    "#f97316",
    "#ef4444",
    "#ec4899",
    "#8b5cf6",
    "#6366f1",
    "#2563eb",
    "#06b6d4",
    "#059669",
    "#84cc16",
    "#a16207",
)


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
