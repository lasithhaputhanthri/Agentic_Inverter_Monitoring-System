"""Deterministic fault scheduler.

Purpose: Plans reproducible, non-overlapping fault scenarios across an inverter fleet.
Inputs: Fleet profiles or device IDs, random seed, time window, and target fault counts.
Outputs: List of validated FaultSpec objects with guaranteed inter-fault separation.
"""

from __future__ import annotations

import random
import re
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from typing import Any

from backend.common.errors import FaultPlanError
from backend.faults.models import FaultSpec, FaultType

MIN_FAULT_GAP_S: float = 600.0  # At least 10 minutes between faults on the same device
DEFAULT_MIN_DURATION_S: float = 600.0  # 10 minutes
DEFAULT_MAX_DURATION_S: float = 1800.0  # 30 minutes
DEVICE_ID_PATTERN = re.compile(r"^INV-\d{2}$")


def _extract_device_ids(fleet: Sequence[Any]) -> list[str]:
    """Validate and extract device IDs from fleet objects or strings."""
    if not fleet:
        raise FaultPlanError("Fleet cannot be empty")

    device_ids: list[str] = []
    for item in fleet:
        d_id = getattr(item, "device_id", item)
        if not isinstance(d_id, str) or not DEVICE_ID_PATTERN.match(d_id):
            raise FaultPlanError(f"Unknown or invalid device ID: {d_id}")
        device_ids.append(d_id)

    # Return unique sorted device IDs
    return sorted(set(device_ids))


def plan_faults(
    fleet: Sequence[Any],
    seed: int,
    start: datetime,
    end: datetime,
    count_per_type: int | dict[FaultType, int],
    min_duration_s: float = DEFAULT_MIN_DURATION_S,
    max_duration_s: float = DEFAULT_MAX_DURATION_S,
) -> list[FaultSpec]:
    """Plan reproducible, non-overlapping fault injections for a fleet.

    Args:
        fleet: Sequence of device profiles or device ID strings (must match INV-XX).
        seed: Random seed ensuring deterministic schedule generation.
        start: UTC start timestamp of the simulation window.
        end: UTC end timestamp of the simulation window.
        count_per_type: Count of faults to schedule per FaultType, or a mapping per type.
        min_duration_s: Minimum fault duration in seconds.
        max_duration_s: Maximum fault duration in seconds.

    Returns:
        List of FaultSpec objects sorted chronologically by start timestamp.

    Raises:
        FaultPlanError: If arguments are invalid or schedule constraints cannot be met.
    """
    device_ids = _extract_device_ids(fleet)

    # Validate timestamps
    if start.tzinfo is None or end.tzinfo is None:
        raise FaultPlanError("Start and end timestamps must be timezone-aware (UTC)")

    start_utc = start.astimezone(UTC)
    end_utc = end.astimezone(UTC)

    if end_utc <= start_utc:
        raise FaultPlanError("End timestamp must be strictly greater than start timestamp")

    total_window_s = (end_utc - start_utc).total_seconds()
    if total_window_s < MIN_FAULT_GAP_S:
        raise FaultPlanError(
            f"Simulation window ({total_window_s}s) is shorter than minimum fault gap ({MIN_FAULT_GAP_S}s)"
        )

    # Determine fault counts
    type_counts: dict[FaultType, int] = {}
    if isinstance(count_per_type, int):
        if count_per_type < 0:
            raise FaultPlanError("count_per_type cannot be negative")
        for ft in FaultType:
            type_counts[ft] = count_per_type
    elif isinstance(count_per_type, dict):
        for ft in FaultType:
            cnt = count_per_type.get(ft, 0)
            if cnt < 0:
                raise FaultPlanError(f"Negative count for fault type: {ft}")
            type_counts[ft] = cnt
    else:
        raise FaultPlanError("count_per_type must be an integer or dict[FaultType, int]")

    total_faults = sum(type_counts.values())
    if total_faults == 0:
        return []

    # Adjust durations if window is constrained
    effective_max_dur = min(max_duration_s, total_window_s)
    effective_min_dur = min(min_duration_s, effective_max_dur)
    if effective_min_dur <= 0:
        effective_min_dur = 60.0

    rng = random.Random(seed)  # nosec: B311

    # Build flat list of fault types to schedule
    fault_types: list[FaultType] = []
    for ft, count in type_counts.items():
        fault_types.extend([ft] * count)

    rng.shuffle(fault_types)

    # Track reserved time intervals per device: list of (start_offset_s, end_offset_s)
    device_reservations: dict[str, list[tuple[float, float]]] = {d: [] for d in device_ids}
    raw_specs: list[tuple[float, float, str, FaultType, float]] = []

    for ft in fault_types:
        duration = round(rng.uniform(effective_min_dur, effective_max_dur), 1)
        severity = round(rng.uniform(0.3, 1.0), 2)

        # Candidate devices shuffled for balanced distribution
        candidate_devices = list(device_ids)
        # Sort candidate devices by number of scheduled faults to balance across fleet
        candidate_devices.sort(key=lambda d: len(device_reservations[d]))

        scheduled = False
        for dev_id in candidate_devices:
            reservations = device_reservations[dev_id]
            # Find available slots on this device
            # An existing fault occupying [s, e] blocks [s - MIN_FAULT_GAP_S - duration, e + MIN_FAULT_GAP_S]
            blocked_intervals: list[tuple[float, float]] = []
            for s, e in reservations:
                b_start = max(0.0, s - MIN_FAULT_GAP_S - duration)
                b_end = min(total_window_s - duration, e + MIN_FAULT_GAP_S)
                if b_start <= b_end:
                    blocked_intervals.append((b_start, b_end))

            # Merge blocked intervals
            blocked_intervals.sort()
            merged_blocked: list[tuple[float, float]] = []
            for b_s, b_e in blocked_intervals:
                if not merged_blocked or merged_blocked[-1][1] < b_s:
                    merged_blocked.append((b_s, b_e))
                else:
                    merged_blocked[-1] = (merged_blocked[-1][0], max(merged_blocked[-1][1], b_e))

            # Complement within [0.0, total_window_s - duration]
            free_slots: list[tuple[float, float]] = []
            curr = 0.0
            max_start = total_window_s - duration
            for b_s, b_e in merged_blocked:
                if curr < b_s:
                    free_slots.append((curr, b_s))
                curr = max(curr, b_e)
            if curr < max_start:
                free_slots.append((curr, max_start))

            if not free_slots:
                continue

            # Pick a slot proportional to length
            total_free = sum(slot_end - slot_start for slot_start, slot_end in free_slots)
            if total_free <= 0:
                continue

            pick = rng.uniform(0.0, total_free)
            accum = 0.0
            chosen_offset = free_slots[0][0]
            for slot_start, slot_end in free_slots:
                slot_len = slot_end - slot_start
                if accum + slot_len >= pick:
                    chosen_offset = round(slot_start + (pick - accum), 1)
                    # Snap to 15-second simulation step boundary for realism
                    chosen_offset = min(slot_end, round(chosen_offset / 15.0) * 15.0)
                    break
                accum += slot_len

            # Record reservation
            reservations.append((chosen_offset, chosen_offset + duration))
            reservations.sort()
            raw_specs.append((chosen_offset, duration, dev_id, ft, severity))
            scheduled = True
            break

        if not scheduled:
            raise FaultPlanError(
                f"Cannot schedule fault {ft} within window: insufficient gap or capacity"
            )

    # Sort raw specs chronologically by start offset
    raw_specs.sort(key=lambda item: item[0])

    # Assign sequential fault IDs
    faults: list[FaultSpec] = []
    for idx, (offset_s, duration, dev_id, ft, severity) in enumerate(raw_specs, start=1):
        fault_ts = start_utc + timedelta(seconds=offset_s)
        faults.append(
            FaultSpec(
                fault_id=f"FLT-{idx:04d}",
                fault_type=ft,
                device_id=dev_id,
                start_ts=fault_ts,
                duration_s=duration,
                severity=severity,
            )
        )

    return faults
