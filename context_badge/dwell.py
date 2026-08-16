"""Foreground dwell tracking with noise filtering and periodic checkpoints."""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable, Protocol

from .surface import surface_label

DEFAULT_NOISE_SECONDS = 8
DEFAULT_CHECKPOINT_SECONDS = 60
MIN_NOISE_SECONDS = 1
MAX_NOISE_SECONDS = 600
MIN_CHECKPOINT_SECONDS = 5
MAX_CHECKPOINT_SECONDS = 3600


class DwellSessionStore(Protocol):
    def load_active(self) -> dict[str, Any] | None: ...
    def save_active(self, session: dict[str, Any] | None) -> None: ...
    def append_session(self, session: dict[str, Any]) -> None: ...


@dataclass(frozen=True)
class DwellObservation:
    executable: str
    app: str
    title: str

    @property
    def key(self) -> tuple[str, str]:
        return self.executable, self.title

    @property
    def surface(self) -> str:
        return surface_label(self.executable, self.title)


class DwellTracker:
    """Record how long a foreground app/page stays on top.

    Stays shorter than ``noise_seconds`` are discarded. Once a stay crosses
    that threshold it is written to the active file, then refreshed every
    ``checkpoint_seconds`` so an unexpected shutdown still has a recent
    duration to recover.
    """

    def __init__(
        self,
        store: DwellSessionStore,
        *,
        noise_seconds: int = DEFAULT_NOISE_SECONDS,
        checkpoint_seconds: int = DEFAULT_CHECKPOINT_SECONDS,
        monotonic: Callable[[], float] = time.monotonic,
        wall_clock: Callable[[], datetime] = lambda: datetime.now().astimezone(),
    ) -> None:
        self.store = store
        self.noise_ms = max(1, int(noise_seconds * 1000))
        self.checkpoint_ms = max(1, int(checkpoint_seconds * 1000))
        self.monotonic = monotonic
        self.wall_clock = wall_clock
        self.current: DwellObservation | None = None
        self.session_id = ""
        self.started_mono = 0.0
        self.started_at = ""
        self.last_mark = -1
        self.persisted = False
        try:
            self._recover()
        except OSError:
            pass

    def observe(self, observation: DwellObservation) -> None:
        try:
            self._observe(observation)
        except OSError:
            # Tracking must never take the overlay down because a write failed.
            return

    def close(self, reason: str = "shutdown") -> None:
        try:
            self._finish(reason)
        except OSError:
            return

    def _recover(self) -> None:
        session = self.store.load_active()
        if not session:
            return
        duration_ms = _int_field(session.get("duration_ms"), 0)
        if duration_ms >= self.noise_ms:
            recovered = dict(session)
            recovered["ended_at"] = str(
                session.get("updated_at") or session.get("started_at") or ""
            )
            recovered["close_reason"] = "crash"
            recovered["duration_ms"] = duration_ms
            self.store.append_session(recovered)
        else:
            self.store.save_active(None)

    def _observe(self, observation: DwellObservation) -> None:
        now = self.monotonic()
        if self.current is None:
            self._begin(observation, now)
            return
        if observation.key != self.current.key:
            self._finish("switch")
            self._begin(observation, now)
            return
        elapsed_ms = int((now - self.started_mono) * 1000)
        if elapsed_ms < self.noise_ms:
            return
        mark = elapsed_ms // self.checkpoint_ms
        if not self.persisted or mark > self.last_mark:
            self._checkpoint(elapsed_ms)
            self.last_mark = mark

    def _begin(self, observation: DwellObservation, now: float) -> None:
        self.current = observation
        self.session_id = uuid.uuid4().hex
        self.started_mono = now
        self.started_at = self.wall_clock().isoformat(timespec="seconds")
        self.last_mark = -1
        self.persisted = False

    def _checkpoint(self, elapsed_ms: int) -> None:
        self.store.save_active(self._session_dict(elapsed_ms))
        self.persisted = True

    def _finish(self, reason: str) -> None:
        if self.current is None:
            return
        elapsed_ms = int((self.monotonic() - self.started_mono) * 1000)
        if elapsed_ms >= self.noise_ms:
            record = self._session_dict(elapsed_ms)
            record["ended_at"] = self.wall_clock().isoformat(timespec="seconds")
            record["close_reason"] = reason
            self.store.append_session(record)
        elif self.persisted:
            self.store.save_active(None)
        self.current = None
        self.persisted = False

    def _session_dict(self, elapsed_ms: int) -> dict[str, Any]:
        assert self.current is not None
        updated_at = self.wall_clock().isoformat(timespec="seconds")
        return {
            "id": self.session_id,
            "executable": self.current.executable,
            "app": self.current.app,
            "title": self.current.title,
            "surface": self.current.surface,
            "started_at": self.started_at,
            "updated_at": updated_at,
            "duration_ms": max(0, elapsed_ms),
        }


def _int_field(value: object, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default
