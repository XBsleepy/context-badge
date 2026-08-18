"""Where the pet sits relative to the badge.

Strategies are named so Menu or config can switch later without rewriting
the overlay. The first shipped layout is ``perch_top``: idle as if sitting
on the badge. ``attach_left`` / ``attach_right`` keep the badge as a chat
bubble with the pet stuck to a side.
"""

from __future__ import annotations

from dataclasses import dataclass

PERCH_TOP = "perch_top"
ATTACH_LEFT = "attach_left"
ATTACH_RIGHT = "attach_right"
PLACEMENTS = (PERCH_TOP, ATTACH_LEFT, ATTACH_RIGHT)
DEFAULT_PLACEMENT = PERCH_TOP
PLACEMENT_CHOICES = (
    (PERCH_TOP, "On badge"),
    (ATTACH_LEFT, "Left"),
    (ATTACH_RIGHT, "Right"),
)
DEFAULT_SCALE_PERCENT = 50
MIN_SCALE_PERCENT = 25
MAX_SCALE_PERCENT = 100


@dataclass(frozen=True)
class BadgeAnchor:
    x: int
    y: int
    width: int
    height: int
    body_width: int = 0


@dataclass(frozen=True)
class PetSize:
    width: int
    height: int


def normalize_placement(value: object) -> str:
    name = str(value or "").strip()
    if name in PLACEMENTS:
        return name
    return DEFAULT_PLACEMENT


def normalize_scale_percent(value: object) -> int:
    """Clamp a pet scale percent into the supported range."""
    try:
        percent = int(round(float(value)))
    except (TypeError, ValueError):
        percent = DEFAULT_SCALE_PERCENT
    return max(MIN_SCALE_PERCENT, min(MAX_SCALE_PERCENT, percent))


def relative_offset(
    placement: str,
    badge: BadgeAnchor,
    pet: PetSize,
    *,
    overlap: int | None = None,
) -> tuple[int, int]:
    """Pet top-left relative to the badge top-left."""
    x, y = place_pet(placement, badge, pet, overlap=overlap)
    return int(x - badge.x), int(y - badge.y)


def keep_sit_offset(
    old: PetSize, new: PetSize, offset: tuple[int, int]
) -> tuple[int, int]:
    """Keep the pet's bottom-centre sit point when the cell size changes."""
    cx = offset[0] + old.width // 2
    bottom = offset[1] + old.height
    return cx - new.width // 2, bottom - new.height


def place_pet(
    placement: str,
    badge: BadgeAnchor,
    pet: PetSize,
    *,
    overlap: int | None = None,
) -> tuple[int, int]:
    """Return the top-left screen point for the pet window."""
    kind = normalize_placement(placement)
    if kind == ATTACH_LEFT:
        return _attach_left(badge, pet, overlap=overlap)
    if kind == ATTACH_RIGHT:
        return _attach_right(badge, pet, overlap=overlap)
    return _perch_top(badge, pet, overlap=overlap)


def _body_width(badge: BadgeAnchor) -> int:
    body = int(badge.body_width) if badge.body_width else int(badge.width)
    return max(1, min(body, int(badge.width)))


def _perch_top(
    badge: BadgeAnchor, pet: PetSize, *, overlap: int | None
) -> tuple[int, int]:
    sit = max(12, pet.height // 5) if overlap is None else int(overlap)
    body = _body_width(badge)
    x = int(badge.x) + (body - pet.width) // 2
    y = int(badge.y) - pet.height + sit
    return x, y


def _attach_left(
    badge: BadgeAnchor, pet: PetSize, *, overlap: int | None
) -> tuple[int, int]:
    tuck = 10 if overlap is None else int(overlap)
    x = int(badge.x) - pet.width + tuck
    y = int(badge.y) + int(badge.height) - pet.height
    return x, y


def _attach_right(
    badge: BadgeAnchor, pet: PetSize, *, overlap: int | None
) -> tuple[int, int]:
    tuck = 10 if overlap is None else int(overlap)
    x = int(badge.x) + int(badge.width) - tuck
    y = int(badge.y) + int(badge.height) - pet.height
    return x, y
