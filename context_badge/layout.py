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
BASE_LIST_HEADER = 40
BASE_LIST_ROW = 44
BASE_LIST_SECTION = 26
BASE_LIST_MAX_BODY = 264
BASE_LIST_RADIUS = 18
BASE_LIST_TAIL = 11
BASE_LIST_ROD = 8
BASE_LIST_CHROME_PAD = 10
MIN_LIST_HEADER = 32
MIN_LIST_ROW = 36
MIN_LIST_SECTION = 22
MIN_LIST_MAX_BODY = 192
MIN_LIST_RADIUS = 14
MIN_LIST_TAIL = 8
MIN_LIST_ROD = 6
MIN_LIST_CHROME_PAD = 8


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
    list_font_size: int
    list_count_font_size: int
    list_header_height: int
    list_row_height: int
    list_section_height: int
    list_max_body: int
    list_radius: int
    list_tail_height: int
    list_rod_height: int
    list_chrome_pad: int


def _scale_px(base: int, scale: float, minimum: int) -> int:
    return max(minimum, round(base * scale))


def _damped_scale(ratio: float, amount: float) -> float:
    """Grow slower than the raw size ratio so leftover space can wrap text."""
    return 1.0 + amount * (max(ratio, 1e-6) - 1.0)


def badge_metrics(
    width: int,
    height: int,
    *,
    default_width: int = 440,
    default_height: int = 72,
) -> BadgeMetrics:
    """Return layout metrics that grow and shrink with the badge.

    Type size follows height, but only part-way, so extra height opens more
    title lines instead of only enlarging letters. Extra width becomes
    wrapping room rather than larger type, which keeps a short-wide badge
    from clipping.
    """
    height_ratio = max(1, height) / default_height
    width_scale = max(1, width) / default_width
    font_scale = _damped_scale(height_ratio, 0.42)
    pos_scale = _damped_scale(height_ratio, 0.28)
    padding_x = _scale_px(BASE_PADDING_X, width_scale**0.5, 12)
    app_y = _scale_px(BASE_APP_Y, pos_scale, 12)
    title_y = _scale_px(BASE_TITLE_Y, pos_scale, app_y + 8)
    text_bottom_gap = _scale_px(BASE_TEXT_BOTTOM_GAP, pos_scale, 6)
    divider_margin = min(
        _scale_px(BASE_DIVIDER_MARGIN, pos_scale, 6),
        max(6, (height - 20) // 2),
    )
    app_font_size = _scale_px(BASE_APP_FONT, font_scale, MIN_APP_FONT)
    title_font_size = _scale_px(BASE_TITLE_FONT, font_scale, MIN_TITLE_FONT)
    return BadgeMetrics(
        app_font_size=app_font_size,
        title_font_size=title_font_size,
        handle_font_size=_scale_px(BASE_HANDLE_FONT, font_scale, MIN_HANDLE_FONT),
        edit_icon_font_size=min(
            MAX_EDIT_ICON_FONT,
            _scale_px(BASE_EDIT_ICON_FONT, font_scale, MIN_EDIT_ICON_FONT),
        ),
        padding_x=padding_x,
        app_y=app_y,
        title_y=title_y,
        text_right_gap=padding_x,
        text_bottom_gap=text_bottom_gap,
        handle_inset_x=_scale_px(BASE_HANDLE_INSET_X, width_scale**0.5, 8),
        handle_inset_y=_scale_px(BASE_HANDLE_INSET_Y, pos_scale, 6),
        edit_button_radius=BASE_EDIT_BUTTON_RADIUS,
        divider_margin=divider_margin,
        list_font_size=title_font_size,
        list_count_font_size=app_font_size,
        list_header_height=_scale_px(BASE_LIST_HEADER, font_scale, MIN_LIST_HEADER),
        list_row_height=_scale_px(BASE_LIST_ROW, font_scale, MIN_LIST_ROW),
        list_section_height=_scale_px(BASE_LIST_SECTION, font_scale, MIN_LIST_SECTION),
        list_max_body=_scale_px(BASE_LIST_MAX_BODY, font_scale, MIN_LIST_MAX_BODY),
        list_radius=_scale_px(BASE_LIST_RADIUS, font_scale, MIN_LIST_RADIUS),
        list_tail_height=_scale_px(BASE_LIST_TAIL, font_scale, MIN_LIST_TAIL),
        list_rod_height=_scale_px(BASE_LIST_ROD, font_scale, MIN_LIST_ROD),
        list_chrome_pad=_scale_px(BASE_LIST_CHROME_PAD, font_scale, MIN_LIST_CHROME_PAD),
    )
