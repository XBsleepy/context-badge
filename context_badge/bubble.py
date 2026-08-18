"""Geometry for the list panel's hanging scroll / chat-bubble chrome."""

from __future__ import annotations

import math
from typing import Any


def unfold_ease(t: float) -> float:
    """Ease-out cubic so the scroll grows quickly, then settles."""
    clamped = min(1.0, max(0.0, float(t)))
    return 1.0 - (1.0 - clamped) ** 3


def _arc(
    cx: float,
    cy: float,
    radius: float,
    start_deg: float,
    end_deg: float,
    steps: int,
) -> list[tuple[float, float]]:
    start = math.radians(start_deg)
    end = math.radians(end_deg)
    points: list[tuple[float, float]] = []
    count = max(2, int(steps))
    for index in range(count + 1):
        angle = start + (end - start) * (index / count)
        points.append((cx + radius * math.cos(angle), cy + radius * math.sin(angle)))
    return points


def bubble_outline(
    width: int,
    height: int,
    *,
    radius: int = 18,
    tail_height: int = 11,
    tail_width: int = 20,
    tail_center: float | None = None,
    inset: int = 2,
    corner_steps: int = 7,
) -> list[float]:
    """Return canvas polygon points for a rounded bubble with a top tail.

    Canvas y grows downward. The tail occupies the top of the window and
    points up toward the badge; the rounded body sits below it.
    """
    width = max(32, int(width))
    height = max(24, int(height))
    inset = max(1, int(inset))
    tail_height = max(6, min(int(tail_height), height // 3))
    tail_width = max(10, int(tail_width))
    x1 = float(inset)
    y1 = float(inset + tail_height)
    x2 = float(width - inset)
    y2 = float(height - inset)
    body_w = x2 - x1
    body_h = y2 - y1
    if body_w < 8 or body_h < 8:
        y1 = float(inset)
        body_h = y2 - y1
    requested = max(0.0, float(radius))
    max_r = min(body_w / 2.0, body_h / 2.0)
    if requested < 1 or max_r < 1:
        radius = 0.0
    else:
        radius = min(max(requested, 2.0), max_r)
    if tail_center is None:
        tail_center = x1 + body_w * 0.28
    tail_center = min(
        max(tail_center, x1 + radius + tail_width / 2),
        x2 - radius - tail_width / 2,
    )
    half = tail_width / 2.0
    apex = (tail_center, float(inset))
    tail_left = (tail_center - half, y1)
    tail_right = (tail_center + half, y1)

    points: list[tuple[float, float]] = []
    if radius < 1:
        points.append((x1, y1))
        points.append(tail_left)
        points.append(apex)
        points.append(tail_right)
        points.append((x2, y1))
        points.append((x2, y2))
        points.append((x1, y2))
    else:
        points.extend(_arc(x1 + radius, y1 + radius, radius, 180, 270, corner_steps))
        points.append(tail_left)
        points.append(apex)
        points.append(tail_right)
        points.extend(_arc(x2 - radius, y1 + radius, radius, 270, 360, corner_steps))
        points.extend(_arc(x2 - radius, y2 - radius, radius, 0, 90, corner_steps))
        points.extend(_arc(x1 + radius, y2 - radius, radius, 90, 180, corner_steps))
    flat: list[float] = []
    for x, y in points:
        flat.append(round(x, 2))
        flat.append(round(y, 2))
    return flat


def rounded_rect_points(
    x1: float,
    y1: float,
    x2: float,
    y2: float,
    *,
    radius: int = 12,
    nw: bool = True,
    ne: bool = True,
    se: bool = True,
    sw: bool = True,
    steps: int = 7,
) -> list[float]:
    """Return canvas polygon points for a rectangle with optional round corners."""
    width = max(1.0, float(x2) - float(x1))
    height = max(1.0, float(y2) - float(y1))
    radius = max(0.0, min(float(radius), width / 2.0, height / 2.0))
    points: list[tuple[float, float]] = []

    def add_corner(
        cx: float,
        cy: float,
        start: float,
        end: float,
        sharp: tuple[float, float],
        rounded: bool,
    ) -> None:
        if rounded and radius >= 1:
            points.extend(_arc(cx, cy, radius, start, end, steps))
        else:
            points.append(sharp)

    add_corner(x1 + radius, y1 + radius, 180, 270, (x1, y1), nw)
    add_corner(x2 - radius, y1 + radius, 270, 360, (x2, y1), ne)
    add_corner(x2 - radius, y2 - radius, 0, 90, (x2, y2), se)
    add_corner(x1 + radius, y2 - radius, 90, 180, (x1, y2), sw)
    flat: list[float] = []
    for x, y in points:
        flat.append(round(x, 2))
        flat.append(round(y, 2))
    return flat


def draw_rounded_panel(
    canvas: Any,
    x1: float,
    y1: float,
    x2: float,
    y2: float,
    *,
    fill: str,
    outline: str,
    radius: int,
    nw: bool = True,
    ne: bool = True,
    se: bool = True,
    sw: bool = True,
    width: int = 1,
    tags: tuple[str, ...] | str = (),
) -> int:
    """Paint a rounded (or sharp) panel onto ``canvas``."""
    return int(
        canvas.create_polygon(
            rounded_rect_points(
                x1, y1, x2, y2, radius=radius, nw=nw, ne=ne, se=se, sw=sw
            ),
            fill=fill,
            outline=outline,
            width=width,
            joinstyle="round",
            tags=tags,
        )
    )


def content_box(
    width: int,
    height: int,
    *,
    tail_height: int,
    radius: int,
    pad: int,
    rod_height: int = 0,
) -> tuple[int, int, int, int]:
    """Return ``(x, y, w, h)`` for widgets inside the bubble body."""
    x = max(int(pad), int(radius) + 2)
    y = int(tail_height) + int(rod_height) + int(pad)
    bottom = int(rod_height) + int(pad)
    inner_w = int(width) - 2 * x
    inner_h = int(height) - y - bottom
    return x, y, max(1, inner_w), max(1, inner_h)


def draw_scroll_bubble(
    canvas: Any,
    width: int,
    height: int,
    *,
    fill: str,
    border: str,
    highlight: str,
    rod_fill: str,
    radius: int,
    tail_height: int,
    tail_width: int,
    rod_height: int = 0,
    inset: int = 2,
) -> None:
    """Paint a hanging paper bubble: top tail, rounded body, inner bevel."""
    canvas.delete("all")
    points = bubble_outline(
        width,
        height,
        radius=radius,
        tail_height=tail_height,
        tail_width=tail_width,
        inset=inset,
    )
    canvas.create_polygon(
        points,
        fill=fill,
        outline=border,
        width=2,
        joinstyle="round",
    )
    if fill == highlight:
        return
    inner_radius = 0 if radius < 1 else max(1, int(radius) - 1)
    inner = bubble_outline(
        width,
        height,
        radius=inner_radius,
        tail_height=tail_height,
        tail_width=max(8, tail_width - 4),
        inset=inset + 1,
    )
    canvas.create_polygon(
        inner,
        fill=fill,
        outline=highlight,
        width=1,
        joinstyle="round",
    )
    crease_y = inset + tail_height + 1
    foot_y = height - inset - 2
    left = inset + max(8, int(radius))
    right = width - inset - max(8, int(radius))
    if right - left > 16:
        canvas.create_line(left, crease_y, right, crease_y, fill=rod_fill)
        canvas.create_line(left, foot_y, right, foot_y, fill=rod_fill)
