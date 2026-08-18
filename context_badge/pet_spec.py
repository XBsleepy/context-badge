"""Codex v2 pet atlas geometry and animation clips."""

from __future__ import annotations

from dataclasses import dataclass

CELL_WIDTH = 192
CELL_HEIGHT = 208
ATLAS_COLUMNS = 8
ATLAS_ROWS_V1 = 9
ATLAS_ROWS_V2 = 11
ATLAS_WIDTH = ATLAS_COLUMNS * CELL_WIDTH
ATLAS_HEIGHT_V1 = ATLAS_ROWS_V1 * CELL_HEIGHT
ATLAS_HEIGHT_V2 = ATLAS_ROWS_V2 * CELL_HEIGHT

IDLE = "idle"
RUNNING_RIGHT = "running-right"
RUNNING_LEFT = "running-left"
WAVING = "waving"
JUMPING = "jumping"
FAILED = "failed"
WAITING = "waiting"
RUNNING = "running"
REVIEW = "review"
LOOK = "look"

ACTIVITY_STATES = (
    IDLE,
    RUNNING_RIGHT,
    RUNNING_LEFT,
    WAITING,
    RUNNING,
    REVIEW,
)
ONESHOT_STATES = (WAVING, JUMPING, FAILED)
LOOK_COUNT = 16


@dataclass(frozen=True)
class PetClip:
    """One atlas row that the state machine can play."""

    name: str
    row: int
    columns: tuple[int, ...]
    durations_ms: tuple[int, ...]
    loop: bool = True
    oneshot: bool = False


@dataclass(frozen=True)
class CellRef:
    row: int
    column: int


CLIPS: dict[str, PetClip] = {
    IDLE: PetClip(
        IDLE, 0, tuple(range(6)), (280, 110, 110, 140, 140, 320), loop=True
    ),
    RUNNING_RIGHT: PetClip(
        RUNNING_RIGHT, 1, tuple(range(8)), (120, 120, 120, 120, 120, 120, 120, 220)
    ),
    RUNNING_LEFT: PetClip(
        RUNNING_LEFT, 2, tuple(range(8)), (120, 120, 120, 120, 120, 120, 120, 220)
    ),
    WAVING: PetClip(
        WAVING, 3, tuple(range(4)), (140, 140, 140, 280), loop=False, oneshot=True
    ),
    JUMPING: PetClip(
        JUMPING, 4, tuple(range(5)), (140, 140, 140, 140, 280), loop=False, oneshot=True
    ),
    FAILED: PetClip(
        FAILED, 5, tuple(range(8)), (140, 140, 140, 140, 140, 140, 140, 240),
        loop=False,
        oneshot=True,
    ),
    WAITING: PetClip(
        WAITING, 6, tuple(range(6)), (150, 150, 150, 150, 150, 260)
    ),
    RUNNING: PetClip(
        RUNNING, 7, tuple(range(6)), (120, 120, 120, 120, 120, 220)
    ),
    REVIEW: PetClip(
        REVIEW, 8, tuple(range(6)), (150, 150, 150, 150, 150, 280)
    ),
}


def cell_origin(row: int, column: int) -> tuple[int, int]:
    """Return the top-left pixel of an atlas cell."""
    return int(column) * CELL_WIDTH, int(row) * CELL_HEIGHT


def look_cell(index: int) -> CellRef:
    """Map a clockwise look index 0-15 onto rows 9-10."""
    slot = int(index) % LOOK_COUNT
    if slot < 8:
        return CellRef(9, slot)
    return CellRef(10, slot - 8)


def look_index_from_angle(degrees: float) -> int:
    """Snap a screen-clockwise angle to the nearest 22.5-degree look cell.

    ``0`` is up. The value is taken modulo 360.
    """
    stepped = (float(degrees) % 360.0) / 22.5
    return int(round(stepped)) % LOOK_COUNT
