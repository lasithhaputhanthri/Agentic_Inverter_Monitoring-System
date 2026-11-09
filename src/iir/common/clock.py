"""System and injectable test clock abstractions.

Purpose: Provides timezone-aware UTC time source and advanceable fake clocks.
Inputs: Target times and advancement durations.
Outputs: Timezone-aware UTC datetimes.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Protocol, runtime_checkable


@runtime_checkable
class Clock(Protocol):
    """Protocol for abstracting real and simulated clocks."""

    def now(self) -> datetime:
        """Return the current timezone-aware UTC datetime."""
        ...


class SystemClock:
    """Clock implementation returning actual system wall-clock UTC time."""

    def now(self) -> datetime:
        """Return real current UTC datetime."""
        return datetime.now(UTC)


class FakeClock:
    """Controllable fake clock for deterministic, fast-forward testing."""

    def __init__(self, initial_time: datetime | None = None) -> None:
        if initial_time is None:
            self._current_time: datetime = datetime(2026, 1, 1, 0, 0, 0, tzinfo=UTC)
        else:
            if initial_time.tzinfo is None:
                self._current_time = initial_time.replace(tzinfo=UTC)
            else:
                self._current_time = initial_time.astimezone(UTC)

    def now(self) -> datetime:
        """Return the simulated current UTC datetime."""
        return self._current_time

    def set(self, target_time: datetime) -> None:
        """Set the clock explicitly to a target time."""
        if target_time.tzinfo is None:
            self._current_time = target_time.replace(tzinfo=UTC)
        else:
            self._current_time = target_time.astimezone(UTC)

    def advance(self, duration: timedelta | float | int) -> None:
        """Advance the simulated time forward by seconds or a timedelta."""
        if isinstance(duration, int | float):
            delta = timedelta(seconds=float(duration))
        else:
            delta = duration
        self._current_time += delta
