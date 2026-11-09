"""Read-only agent tools for retrieving telemetry context.

Purpose: Provides deterministic read-only access to historical device telemetry and fleet state.
Inputs: Inverter device IDs, time window in minutes, and exclusions.
Outputs: Sanitized, rounded telemetry records and fleet snapshot dictionaries.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from datetime import UTC, datetime, timedelta
from typing import Any

from backend.common.schemas import TelemetryMessage

MAX_TELEMETRY_SAMPLES: int = 60
MIN_MINUTES: int = 1
MAX_MINUTES: int = 30


class TelemetryStore:
    """In-memory read-only provider for recent telemetry samples across fleet inverters."""

    def __init__(self, messages: Sequence[TelemetryMessage] | None = None) -> None:
        self._history: list[TelemetryMessage] = list(messages) if messages else []

    def add(self, message: TelemetryMessage) -> None:
        """Append a message to the historical buffer."""
        self._history.append(message)

    def get_recent(
        self, device_id: str, minutes: int, current_ts: datetime | None = None
    ) -> list[dict[str, Any]]:
        """Retrieve up to 60 readings for device_id within the last clamped minutes."""
        clamped_minutes = max(MIN_MINUTES, min(MAX_MINUTES, minutes))
        if current_ts is not None:
            now = current_ts if current_ts.tzinfo else current_ts.replace(tzinfo=UTC)
        else:
            dev_ts = [
                m.ts if m.ts.tzinfo else m.ts.replace(tzinfo=UTC)
                for m in self._history
                if m.device_id == device_id
            ]
            now = max(dev_ts) if dev_ts else datetime.now(UTC)

        cutoff = now - timedelta(minutes=clamped_minutes)

        matching = [
            m
            for m in self._history
            if m.device_id == device_id
            and (m.ts if m.ts.tzinfo else m.ts.replace(tzinfo=UTC)) >= cutoff
        ]
        # Sort newest last, clamp to at most 60 samples
        matching.sort(key=lambda x: x.ts)
        sampled = matching[-MAX_TELEMETRY_SAMPLES:]

        return [
            {
                "ts": m.ts.isoformat(),
                "ac_power_w": round(m.ac_power_w, 1),
                "grid_voltage_v": round(m.grid_voltage_v, 1),
                "temperature_c": round(m.temperature_c, 1),
                "relay_state": m.relay_state,
                "status": m.status,
            }
            for m in sampled
        ]

    def get_snapshot(self, exclude_device_id: str) -> dict[str, dict[str, Any]]:
        """Return the latest reading for up to 19 other fleet devices with rounded metrics."""
        latest_by_dev: dict[str, TelemetryMessage] = {}
        for m in self._history:
            if m.device_id != exclude_device_id:
                curr = latest_by_dev.get(m.device_id)
                if curr is None or m.ts > curr.ts:
                    latest_by_dev[m.device_id] = m

        snapshot: dict[str, dict[str, Any]] = {}
        for dev_id, m in sorted(latest_by_dev.items())[:19]:
            snapshot[dev_id] = {
                "ts": m.ts.isoformat(),
                "ac_power_w": round(m.ac_power_w, 1),
                "grid_voltage_v": round(m.grid_voltage_v, 1),
                "temperature_c": round(m.temperature_c, 1),
                "relay_state": m.relay_state,
                "status": m.status,
            }
        return snapshot


# Module-level default store
_DEFAULT_STORE = TelemetryStore()


def set_telemetry_store(store: TelemetryStore) -> None:
    """Set the active telemetry store used by the tool functions."""
    global _DEFAULT_STORE
    _DEFAULT_STORE = store


def get_recent_telemetry(
    device_id: str,
    minutes: int = 15,
    store: TelemetryStore | None = None,
    current_ts: datetime | None = None,
) -> list[dict[str, Any]]:
    """Tool: Retrieve recent telemetry readings for an inverter, clamped to 1-30 minutes and max 60 samples."""
    active_store = store or _DEFAULT_STORE
    return active_store.get_recent(device_id, minutes, current_ts=current_ts)


def get_fleet_snapshot(
    exclude_device_id: str,
    store: TelemetryStore | None = None,
) -> dict[str, dict[str, Any]]:
    """Tool: Retrieve latest rounded telemetry snapshot for up to 19 other inverters in the fleet."""
    active_store = store or _DEFAULT_STORE
    return active_store.get_snapshot(exclude_device_id)


# Fixed read-only tool registry
TOOL_REGISTRY: dict[str, Callable[..., Any]] = {
    "get_recent_telemetry": get_recent_telemetry,
    "get_fleet_snapshot": get_fleet_snapshot,
}
