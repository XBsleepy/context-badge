"""Playable pet state machine. Idle is the only driver for now."""

from __future__ import annotations

from .pet_spec import (
    ACTIVITY_STATES,
    CLIPS,
    IDLE,
    LOOK,
    ONESHOT_STATES,
    CellRef,
    PetClip,
    look_cell,
)


class PetMachine:
    """Tracks the resting activity, one-shots, and optional look pose.

    ``request`` sets a looping activity such as idle or waiting.
    ``pulse`` plays a one-shot then returns to the activity.
    ``set_look_index`` overlays a look cell while idle; later states can
    ignore it until they opt in.
    """

    def __init__(self, clips: dict[str, PetClip] | None = None) -> None:
        self._clips = clips if clips is not None else CLIPS
        self._activity = IDLE
        self._oneshot: str | None = None
        self._look_index: int | None = None
        self._frame = 0

    @property
    def activity(self) -> str:
        return self._activity

    @property
    def look_index(self) -> int | None:
        return self._look_index

    @property
    def state(self) -> str:
        if self._oneshot is not None:
            return self._oneshot
        if self._look_index is not None and self._activity == IDLE:
            return LOOK
        return self._activity

    def request(self, state: str) -> None:
        """Switch the looping activity. Unknown names fall back to idle."""
        if state not in ACTIVITY_STATES or state not in self._clips:
            state = IDLE
        if self._activity == state and self._oneshot is None:
            return
        self._activity = state
        self._oneshot = None
        self._frame = 0

    def pulse(self, state: str) -> None:
        """Play a one-shot clip, then resume the current activity."""
        clip = self._clips.get(state)
        if clip is None or not clip.oneshot:
            if state in ONESHOT_STATES:
                return
            self.request(state)
            return
        self._oneshot = state
        self._frame = 0

    def set_look_index(self, index: int | None) -> None:
        """Show look-direction ``index`` (0-15) while idle, or ``None``."""
        if index is None:
            self._look_index = None
            return
        self._look_index = int(index) % 16

    def current_cell(self) -> CellRef:
        if self._oneshot is None and self._look_index is not None and self._activity == IDLE:
            return look_cell(self._look_index)
        clip = self._active_clip()
        column = clip.columns[min(self._frame, len(clip.columns) - 1)]
        return CellRef(clip.row, column)

    def current_delay_ms(self) -> int:
        if self._oneshot is None and self._look_index is not None and self._activity == IDLE:
            return 120
        clip = self._active_clip()
        index = min(self._frame, len(clip.durations_ms) - 1)
        return max(16, int(clip.durations_ms[index]))

    def advance(self) -> None:
        """Move to the next frame of the active clip."""
        if self._oneshot is None and self._look_index is not None and self._activity == IDLE:
            return
        clip = self._active_clip()
        self._frame += 1
        if self._frame >= len(clip.columns):
            if clip.oneshot:
                self._oneshot = None
            self._frame = 0

    def step(self) -> tuple[CellRef, int]:
        """Return the current cell, then advance. Used by tests and the player."""
        cell = self.current_cell()
        delay = self.current_delay_ms()
        self.advance()
        return cell, delay

    def _active_clip(self) -> PetClip:
        name = self._oneshot or self._activity
        clip = self._clips.get(name)
        if clip is None:
            return self._clips[IDLE]
        return clip
