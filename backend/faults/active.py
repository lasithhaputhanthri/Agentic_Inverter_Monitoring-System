"""Pure query functions for active faults.

Purpose: Determines which scheduled faults are active at any simulation timestamp.
Inputs: Sequence of FaultSpec instances, target timestamp, and optional device ID.
Outputs: List of active FaultSpec instances or single active FaultSpec for a device.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime, timedelta

from backend.faults.models import FaultSpec


def is_fault_active(fault: FaultSpec, ts: datetime) -> bool:
    """Check if a specific fault is active at the given timestamp."""
    ts_utc = ts.astimezone(UTC) if ts.tzinfo is not None else ts.replace(tzinfo=UTC)
    end_ts = fault.start_ts + timedelta(seconds=fault.duration_s)
    return fault.start_ts <= ts_utc < end_ts


def get_active_faults(faults: Sequence[FaultSpec], ts: datetime) -> list[FaultSpec]:
    """Return all faults active across the fleet at the given timestamp."""
    return [f for f in faults if is_fault_active(f, ts)]


def get_active_fault_for_device(
    faults: Sequence[FaultSpec],
    device_id: str,
    ts: datetime,
) -> FaultSpec | None:
    """Return the active fault affecting a specific device at the given timestamp, or None."""
    for f in faults:
        if f.device_id == device_id and is_fault_active(f, ts):
            return f
    return None
