"""Periodic rest reminder driven by Tk ``after`` callbacks."""

from __future__ import annotations

import time
import tkinter as tk
from collections.abc import Callable

DEFAULT_REST_MINUTES = 60
MIN_REST_MINUTES = 1
MAX_REST_MINUTES = 180
PRESET_REST_MINUTES = (15, 30, 60)
CUSTOM_REST_SLOTS = 3
DEFAULT_REST_SECONDS = DEFAULT_REST_MINUTES * 60
DEFAULT_REST_MESSAGE = "Time to rest"
DEFAULT_RESTING_NOTICE = "Resting. Tap Ack when you're back."
MAX_REST_MESSAGE = 80
REST_ALERT_PET = "pet"
REST_ALERT_WINDOW = "window"
REST_ALERT_STYLES = (REST_ALERT_PET, REST_ALERT_WINDOW)
DEFAULT_REST_ALERT = REST_ALERT_PET


def normalize_rest_alert_style(value: object) -> str:
    text = str(value or DEFAULT_REST_ALERT).strip().lower()
    if text in ("window", "dialog", "popup"):
        return REST_ALERT_WINDOW
    if text in ("pet", "bubble", "toast"):
        return REST_ALERT_PET
    return DEFAULT_REST_ALERT


def normalize_rest_minutes(value: object) -> int:
    try:
        minutes = int(round(float(value)))
    except (TypeError, ValueError):
        minutes = DEFAULT_REST_MINUTES
    return max(MIN_REST_MINUTES, min(MAX_REST_MINUTES, minutes))


def minutes_from_seconds(value: object) -> int:
    try:
        seconds = int(round(float(value)))
    except (TypeError, ValueError):
        return DEFAULT_REST_MINUTES
    if seconds < 60:
        return MIN_REST_MINUTES
    return normalize_rest_minutes(seconds / 60)


def normalize_rest_seconds(value: object) -> int:
    return minutes_from_seconds(value) * 60


def format_rest_interval(seconds: int) -> str:
    return f"{minutes_from_seconds(seconds)}m"


def normalize_rest_message(value: object) -> str:
    text = str(value or "").replace("\r", " ").replace("\n", " ").strip()
    while "  " in text:
        text = text.replace("  ", " ")
    if not text:
        return DEFAULT_REST_MESSAGE
    return text[:MAX_REST_MESSAGE]


def normalize_custom_minutes(value: object) -> list[int | None]:
    raw = value if isinstance(value, list) else []
    slots: list[int | None] = []
    for index in range(CUSTOM_REST_SLOTS):
        if index >= len(raw) or raw[index] in (None, "", 0, "0"):
            slots.append(None)
            continue
        slots.append(normalize_rest_minutes(raw[index]))
    return slots


def seed_custom_minutes(
    customs: list[int | None],
    minutes: int,
) -> list[int | None]:
    slots = list(customs)
    chosen = normalize_rest_minutes(minutes)
    if chosen in PRESET_REST_MINUTES or chosen in slots:
        return slots
    for index, value in enumerate(slots):
        if value is None:
            slots[index] = chosen
            break
    return slots


def normalize_custom_slot(
    value: object,
    customs: list[int | None],
    minutes: int,
) -> int | None:
    chosen = normalize_rest_minutes(minutes)
    slot: int | None = None
    try:
        if value is not None and value != "":
            slot = int(value)
    except (TypeError, ValueError):
        slot = None
    if slot is not None and 0 <= slot < len(customs) and customs[slot] == chosen:
        return slot
    if chosen in PRESET_REST_MINUTES:
        return None
    for index, stored in enumerate(customs):
        if stored == chosen:
            return index
    return None


def custom_slot_is_selected(
    slot: int,
    *,
    minutes: int,
    customs: list[int | None],
    selected_slot: int | None,
) -> bool:
    if slot < 0 or slot >= len(customs) or customs[slot] is None:
        return False
    chosen = normalize_rest_minutes(minutes)
    if selected_slot is not None:
        return selected_slot == slot
    if chosen in PRESET_REST_MINUTES:
        return False
    return customs[slot] == chosen


def format_countdown(ms: int) -> str:
    total = max(0, int(ms) // 1000)
    minutes, secs = divmod(total, 60)
    if minutes >= 60:
        hours, minutes = divmod(minutes, 60)
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"


class RestTimer:
    """Wall-clock rest alarm. Pause freezes the countdown; Off cancels it."""

    def __init__(
        self,
        root: tk.Misc,
        *,
        on_fire: Callable[[], None] | None = None,
        on_tick: Callable[[], None] | None = None,
    ) -> None:
        self._root = root
        self._on_fire = on_fire
        self._on_tick = on_tick
        self.enabled = False
        self.paused = False
        self.seconds = DEFAULT_REST_SECONDS
        self._job: str | None = None
        self._tick_job: str | None = None
        self._deadline: float | None = None
        self._remaining_ms: int | None = None
        self.awaiting = False

    def configure(
        self,
        *,
        enabled: bool | None = None,
        paused: bool | None = None,
        seconds: int | None = None,
        awaiting: bool | None = None,
    ) -> None:
        if (
            paused is True
            and not self.paused
            and self.enabled
            and self._deadline is not None
        ):
            self._remaining_ms = int(
                max(1, (self._deadline - time.monotonic()) * 1000)
            )
        if enabled is False:
            self._remaining_ms = None
            self.awaiting = False
        if paused is True:
            self.awaiting = False
        if enabled is not None:
            self.enabled = bool(enabled)
        if paused is not None:
            self.paused = bool(paused)
        if seconds is not None:
            previous = self.seconds
            self.seconds = normalize_rest_seconds(seconds)
            if self.seconds != previous:
                self._remaining_ms = None
        if awaiting is not None:
            self.awaiting = bool(awaiting) and self.enabled and not self.paused
        if self.enabled and not self.paused and awaiting is False:
            self._remaining_ms = None
        self._resync()

    def acknowledge(self) -> None:
        """Start the next work interval after a rest."""
        if not self.enabled:
            return
        self.paused = False
        self.awaiting = False
        self._remaining_ms = None
        self._resync()

    def stop(self) -> None:
        self._cancel()
        self._cancel_tick()
        self._deadline = None
        self._remaining_ms = None
        self.awaiting = False

    def remaining_ms(self) -> int:
        if not self.enabled:
            return 0
        if self.awaiting:
            return 0
        if self.paused:
            if self._remaining_ms is not None:
                return max(0, int(self._remaining_ms))
            return self.seconds * 1000
        if self._deadline is None:
            return self.seconds * 1000
        return max(0, int((self._deadline - time.monotonic()) * 1000))

    def _resync(self) -> None:
        self._cancel()
        self._cancel_tick()
        if not self.enabled:
            self._deadline = None
            self._remaining_ms = None
            self.awaiting = False
            return
        if self.awaiting:
            self._deadline = None
            self._remaining_ms = 0
            self._arm_tick()
            return
        if self.paused:
            if self._remaining_ms is None:
                self._remaining_ms = self.seconds * 1000
            self._deadline = None
            self._arm_tick()
            return
        remaining = (
            self._remaining_ms
            if self._remaining_ms is not None
            else self.seconds * 1000
        )
        remaining = max(1, int(remaining))
        self._remaining_ms = None
        self._deadline = time.monotonic() + remaining / 1000.0
        try:
            self._job = self._root.after(remaining, self._fire)
        except tk.TclError:
            self._job = None
        self._arm_tick()

    def _cancel(self) -> None:
        if self._job is None:
            return
        try:
            self._root.after_cancel(self._job)
        except tk.TclError:
            pass
        self._job = None

    def _cancel_tick(self) -> None:
        if self._tick_job is None:
            return
        try:
            self._root.after_cancel(self._tick_job)
        except tk.TclError:
            pass
        self._tick_job = None

    def _arm_tick(self) -> None:
        if self._on_tick is None or not self.enabled:
            return
        try:
            self._tick_job = self._root.after(250, self._tick)
        except tk.TclError:
            self._tick_job = None

    def _tick(self) -> None:
        self._tick_job = None
        if self._on_tick is not None and self.enabled:
            try:
                self._on_tick()
            except tk.TclError:
                return
        if self.enabled:
            self._arm_tick()

    def _fire(self) -> None:
        self._job = None
        self._deadline = None
        self._remaining_ms = None
        if not self.enabled or self.paused:
            return
        self.awaiting = True
        self._resync()
        if self._on_fire is not None:
            try:
                self._on_fire()
            except tk.TclError:
                return

    def pause(self) -> None:
        if not self.enabled or self.paused:
            return
        if self._deadline is not None:
            left = int(max(1, (self._deadline - time.monotonic()) * 1000))
            self._remaining_ms = left
        self.paused = True
        self.awaiting = False
        self._resync()

    def resume(self) -> None:
        if not self.enabled or not self.paused:
            return
        self.paused = False
        self._resync()
