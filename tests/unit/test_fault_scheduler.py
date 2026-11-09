"""Unit tests for the fault scheduler.

Purpose: Verifies reproducibility, zero-overlap guarantee, 10-minute minimum separation,
         and error handling in deterministic fault planning.
Inputs: Fleet fixtures, time ranges, and fault counts.
Outputs: Pytest assertions verifying schedule validity.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from backend.common.errors import FaultPlanError
from backend.faults.models import FaultType
from backend.faults.scheduler import MIN_FAULT_GAP_S, plan_faults
from simulator.devices import make_fleet


def test_plan_faults_reproducible() -> None:
    """Ensure plan_faults produces identical outputs given the same seed."""
    fleet = [f"INV-{i:02d}" for i in range(1, 21)]
    start = datetime(2026, 6, 1, 0, 0, 0, tzinfo=UTC)
    end = start + timedelta(days=2)

    plan1 = plan_faults(fleet, seed=42, start=start, end=end, count_per_type=3)
    plan2 = plan_faults(fleet, seed=42, start=start, end=end, count_per_type=3)

    assert len(plan1) == len(plan2) == 12  # 3 faults * 4 fault types
    for f1, f2 in zip(plan1, plan2, strict=True):
        assert f1.model_dump() == f2.model_dump()


def test_plan_faults_different_seeds_produce_different_plans() -> None:
    """Ensure different seeds produce distinct schedules."""
    fleet = [f"INV-{i:02d}" for i in range(1, 21)]
    start = datetime(2026, 6, 1, 0, 0, 0, tzinfo=UTC)
    end = start + timedelta(days=2)

    plan1 = plan_faults(fleet, seed=42, start=start, end=end, count_per_type=2)
    plan2 = plan_faults(fleet, seed=99, start=start, end=end, count_per_type=2)

    assert [f.start_ts for f in plan1] != [f.start_ts for f in plan2]


def test_plan_faults_no_overlaps_and_minimum_gap() -> None:
    """Verify that no device experiences overlapping faults and inter-fault gaps exceed 10 minutes."""
    fleet = [f"INV-{i:02d}" for i in range(1, 11)]
    start = datetime(2026, 6, 1, 0, 0, 0, tzinfo=UTC)
    end = start + timedelta(days=3)

    plan = plan_faults(fleet, seed=123, start=start, end=end, count_per_type=5)
    assert len(plan) == 20

    # Group by device
    by_device: dict[str, list] = {d: [] for d in fleet}
    for f in plan:
        by_device[f.device_id].append(f)

    for dev_id, faults in by_device.items():
        faults.sort(key=lambda x: x.start_ts)
        for i in range(len(faults) - 1):
            curr_end = faults[i].start_ts + timedelta(seconds=faults[i].duration_s)
            next_start = faults[i + 1].start_ts
            gap_s = (next_start - curr_end).total_seconds()
            assert gap_s >= MIN_FAULT_GAP_S, (
                f"Device {dev_id} has gap of {gap_s}s between {faults[i].fault_id} "
                f"and {faults[i + 1].fault_id}, expected >= {MIN_FAULT_GAP_S}s"
            )


def test_plan_faults_rejects_unknown_device_ids() -> None:
    """Verify that plan_faults raises FaultPlanError on invalid device IDs."""
    start = datetime(2026, 6, 1, 0, 0, 0, tzinfo=UTC)
    end = start + timedelta(days=1)

    # Empty fleet
    with pytest.raises(FaultPlanError, match="Fleet cannot be empty"):
        plan_faults([], seed=42, start=start, end=end, count_per_type=1)

    # Invalid device format
    with pytest.raises(FaultPlanError, match="Unknown or invalid device ID"):
        plan_faults(["INV-999"], seed=42, start=start, end=end, count_per_type=1)

    with pytest.raises(FaultPlanError, match="Unknown or invalid device ID"):
        plan_faults(["BAD_NAME"], seed=42, start=start, end=end, count_per_type=1)


def test_plan_faults_rejects_invalid_time_windows() -> None:
    """Verify that plan_faults validates time windows."""
    fleet = ["INV-01", "INV-02"]
    start = datetime(2026, 6, 1, 12, 0, 0, tzinfo=UTC)

    # End before start
    with pytest.raises(FaultPlanError, match="End timestamp must be strictly greater"):
        plan_faults(fleet, seed=42, start=start, end=start - timedelta(hours=1), count_per_type=1)

    # Window shorter than minimum gap
    with pytest.raises(FaultPlanError, match="shorter than minimum fault gap"):
        plan_faults(
            fleet, seed=42, start=start, end=start + timedelta(seconds=300), count_per_type=1
        )


def test_plan_faults_100_faults_7_days_zero_overlaps() -> None:
    """Acceptance test: 100 faults across 20 devices over 7 simulated days has zero overlaps.

    Records the result and inter-fault gap statistics.
    """
    fleet = make_fleet(20, seed=42)
    start = datetime(2026, 6, 1, 0, 0, 0, tzinfo=UTC)
    end = start + timedelta(days=7)

    # 100 faults total = 25 per type across 4 fault types
    plan = plan_faults(fleet, seed=42, start=start, end=end, count_per_type=25)

    assert len(plan) == 100, f"Expected exactly 100 planned faults, got {len(plan)}"

    # Check distribution across fault types
    type_counts = {ft: 0 for ft in FaultType}
    for f in plan:
        type_counts[f.fault_type] += 1
    for ft, count in type_counts.items():
        assert count == 25, f"Expected 25 of {ft}, got {count}"

    # Group by device and verify inter-fault separation
    device_faults: dict[str, list] = {d.device_id: [] for d in fleet}
    for f in plan:
        device_faults[f.device_id].append(f)

    overlaps_count = 0
    min_gap_observed = float("inf")

    for dev_id, faults in device_faults.items():
        faults.sort(key=lambda x: x.start_ts)
        for i in range(len(faults) - 1):
            curr_end = faults[i].start_ts + timedelta(seconds=faults[i].duration_s)
            next_start = faults[i + 1].start_ts
            gap_s = (next_start - curr_end).total_seconds()
            if gap_s < 0:
                overlaps_count += 1
            if gap_s < min_gap_observed:
                min_gap_observed = gap_s
            assert gap_s >= MIN_FAULT_GAP_S, (
                f"Overlap or small gap on {dev_id}: {gap_s}s (< {MIN_FAULT_GAP_S}s)"
            )

    assert overlaps_count == 0, f"Expected 0 overlaps, found {overlaps_count}"
    assert min_gap_observed >= MIN_FAULT_GAP_S
    print(
        f"\n[Result Recorded] 100 faults scheduled across 20 devices over 7 days: "
        f"Overlaps = {overlaps_count}, Minimum observed gap = {min_gap_observed:.1f}s (required >= {MIN_FAULT_GAP_S}s)"
    )
