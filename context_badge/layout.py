"""Size-dependent layout metrics for the badge canvas."""

from __future__ import annotations

from dataclasses import dataclass

BASE_APP_FONT = 10
BASE_TITLE_FONT = 13
BASE_HANDLE_FONT = 11
BASE_EDIT_ICON_FONT = 13
BASE_PADDING_X = 22
BASE_APP_Y = 19
BASE_TITLE_Y = 38
BASE_HANDLE_INSET_X = 10
BASE_HANDLE_INSET_Y = 8
BASE_TEXT_BOTTOM_GAP = 8
BASE_EDIT_BUTTON_RADIUS = 15
BASE_DIVIDER_MARGIN = 10
MIN_APP_FONT = 7
MIN_TITLE_FONT = 9
MIN_HANDLE_FONT = 8
MIN_EDIT_ICON_FONT = 11
MAX_EDIT_ICON_FONT = 16


@dataclass(frozen=True)
class BadgeMetrics:
    """Canvas measurements that follow the current badge size."""

    app_font_size: int
    title_font_size: int
    handle_font_size: int
    edit_icon_font_size: int
    padding_x: int
    app_y: int
    title_y: int
    text_right_gap: int
    text_bottom_gap: int
    handle_inset_x: int
    handle_inset_y: int
    edit_button_radius: int
    divider_margin: int


def _scale_px(base: int, scale: float, minimum: int) -> int:
    return max(minimum, round(base * scale))


def badge_metrics(
    width: int,
    height: int,
    *,
    default_width: int = 440,
    default_height: int = 72,
) -> BadgeMetrics:
    """Return layout metrics that grow and shrink with the badge.

    Type size follows height so a taller overlay is easier to read. Extra
    width becomes wrapping room rather than larger letters, which keeps a
    short-wide badge from clipping.
    """
    height_scale = max(1, height) / default_height
    width_scale = max(1, width) / default_width
    padding_x = _scale_px(BASE_PADDING_X, width_scale**0.5, 12)
    app_y = _scale_px(BASE_APP_Y, height_scale, 12)
    title_y = _scale_px(BASE_TITLE_Y, height_scale, app_y + 8)
    text_bottom_gap = _scale_px(BASE_TEXT_BOTTOM_GAP, height_scale, 6)
    divider_margin = min(
        _scale_px(BASE_DIVIDER_MARGIN, height_scale, 6),
        max(6, (height - 20) // 2),
    )
    return BadgeMetrics(
        app_font_size=_scale_px(BASE_APP_FONT, height_scale, MIN_APP_FONT),
        title_font_size=_scale_px(BASE_TITLE_FONT, height_scale, MIN_TITLE_FONT),
        handle_font_size=_scale_px(BASE_HANDLE_FONT, height_scale, MIN_HANDLE_FONT),
        edit_icon_font_size=min(
            MAX_EDIT_ICON_FONT,
            _scale_px(BASE_EDIT_ICON_FONT, height_scale, MIN_EDIT_ICON_FONT),
        ),
        padding_x=padding_x,
        app_y=app_y,
        title_y=title_y,
        text_right_gap=padding_x,
        text_bottom_gap=text_bottom_gap,
        handle_inset_x=_scale_px(BASE_HANDLE_INSET_X, width_scale**0.5, 8),
        handle_inset_y=_scale_px(BASE_HANDLE_INSET_Y, height_scale, 6),
        edit_button_radius=BASE_EDIT_BUTTON_RADIUS,
        divider_margin=divider_margin,
    )
