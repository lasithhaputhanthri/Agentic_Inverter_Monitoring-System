"""Unit tests for fault injection behaviors.

Purpose: Verifies the physical signatures of overheating, grid sag, relay stuck,
         and comm dropout faults across simulated time windows.
Inputs: Baseline TelemetryMessage fixtures and FaultSpec scenarios.
Outputs: Pytest assertions verifying mathematical and physical accuracy of injected faults.
"""

from __future__ import annotations

import random
from datetime import UTC, datetime, timedelta

import pytest
from backend.common.clock import FakeClock
from backend.common.schemas import TelemetryMessage
from backend.faults.injector import (
    FaultSession,
    apply_fault,
    inject_comm_dropout,
    inject_grid_sag,
    inject_overheating,
    inject_relay_stuck,
)
from backend.faults.models import FaultSpec, FaultType
from simulator.devices import DeviceProfile, make_fleet
from simulator.runner import SimulationRunner


def _make_base_msg(
    device_id: str = "INV-01",
    ts: datetime | None = None,
    power_w: float = 3000.0,
    grid_v: float = 230.0,
    temp_c: float = 45.0,
    relay: str = "closed",
    status: str = "normal",
) -> TelemetryMessage:
    """Helper creating a baseline telemetry message."""
    return TelemetryMessage(
        device_id=device_id,
        ts=ts or datetime(2026, 6, 1, 12, 0, 0, tzinfo=UTC),
        ac_power_w=power_w,
        dc_voltage_v=400.0,
        grid_voltage_v=grid_v,
        temperature_c=temp_c,
        relay_state=relay,  # type: ignore[arg-type]
        status=status,  # type: ignore[arg-type]
    )


def test_inject_overheating_thermal_ramp() -> None:
    """Verify overheating ramps over 5 minutes (300s) then holds steady."""
    start = datetime(2026, 6, 1, 12, 0, 0, tzinfo=UTC)
    fault = FaultSpec(
        fault_id="FLT-0001",
        fault_type=FaultType.OVERHEATING,
        device_id="INV-01",
        start_ts=start,
        duration_s=600.0,
        severity=1.0,  # Max severity -> 30 degrees increase
    )
    base_temp = 40.0
    msg = _make_base_msg(ts=start, temp_c=base_temp)

    # At start (t=0s), ramp = 0 -> temp = base
    t0_msg = inject_overheating(msg, fault, start)
    assert t0_msg.temperature_c == base_temp

    # At halfway through ramp (t=150s), ramp = 0.5 -> temp = base + 15
    t150_msg = inject_overheating(msg, fault, start + timedelta(seconds=150))
    assert t150_msg.temperature_c == pytest.approx(base_temp + 15.0, abs=0.1)

    # At ramp completion (t=300s), ramp = 1.0 -> temp = base + 30
    t300_msg = inject_overheating(msg, fault, start + timedelta(seconds=300))
    assert t300_msg.temperature_c == pytest.approx(base_temp + 30.0, abs=0.1)

    # At t=450s (holding steady), ramp = 1.0 -> temp = base + 30
    t450_msg = inject_overheating(msg, fault, start + timedelta(seconds=450))
    assert t450_msg.temperature_c == pytest.approx(base_temp + 30.0, abs=0.1)


def test_inject_overheating_severity_scaling() -> None:
    """Verify overheating delta scales between 15 C (severity 0.0) and 30 C (severity 1.0)."""
    start = datetime(2026, 6, 1, 12, 0, 0, tzinfo=UTC)
    base_temp = 40.0
    msg = _make_base_msg(ts=start + timedelta(seconds=300), temp_c=base_temp)

    # Severity 0.0 -> 15 C increase
    f_min = FaultSpec(
        fault_id="FLT-0001",
        fault_type=FaultType.OVERHEATING,
        device_id="INV-01",
        start_ts=start,
        duration_s=600.0,
        severity=0.0,
    )
    res_min = inject_overheating(msg, f_min, start + timedelta(seconds=300))
    assert res_min.temperature_c == pytest.approx(55.0, abs=0.1)

    # Severity 0.5 -> 22.5 C increase
    f_mid = FaultSpec(
        fault_id="FLT-0002",
        fault_type=FaultType.OVERHEATING,
        device_id="INV-01",
        start_ts=start,
        duration_s=600.0,
        severity=0.5,
    )
    res_mid = inject_overheating(msg, f_mid, start + timedelta(seconds=300))
    assert res_mid.temperature_c == pytest.approx(62.5, abs=0.1)


def test_inject_grid_sag_voltage_range() -> None:
    """Verify grid sag keeps voltage between 180 V and 205 V with noise."""
    start = datetime(2026, 6, 1, 12, 0, 0, tzinfo=UTC)
    rng = random.Random(42)  # nosec: B311
    msg = _make_base_msg(grid_v=230.0)

    for sev in (0.0, 0.25, 0.5, 0.75, 1.0):
        fault = FaultSpec(
            fault_id="FLT-0001",
            fault_type=FaultType.GRID_SAG,
            device_id="INV-01",
            start_ts=start,
            duration_s=600.0,
            severity=sev,
        )
        res = inject_grid_sag(msg, fault, rng=rng)
        assert 180.0 <= res.grid_voltage_v <= 205.0


def test_inject_relay_stuck_behavior() -> None:
    """Verify relay stuck reports open and transitions to warning when power > 200 W."""
    start = datetime(2026, 6, 1, 12, 0, 0, tzinfo=UTC)
    fault = FaultSpec(
        fault_id="FLT-0001",
        fault_type=FaultType.RELAY_STUCK,
        device_id="INV-01",
        start_ts=start,
        duration_s=600.0,
        severity=1.0,
    )

    # Power > 200 W: open and warning
    daylight_msg = _make_base_msg(power_w=1500.0, relay="closed", status="normal")
    res_daylight = inject_relay_stuck(daylight_msg, fault)
    assert res_daylight.relay_state == "open"
    assert res_daylight.status == "warning"

    # Power <= 200 W: open
    night_msg = _make_base_msg(power_w=50.0, relay="closed", status="normal")
    res_night = inject_relay_stuck(night_msg, fault)
    assert res_night.relay_state == "open"


def test_inject_comm_dropout_suppression() -> None:
    """Verify comm dropout returns None, suppressing telemetry publishing."""
    start = datetime(2026, 6, 1, 12, 0, 0, tzinfo=UTC)
    fault = FaultSpec(
        fault_id="FLT-0001",
        fault_type=FaultType.COMM_DROPOUT,
        device_id="INV-01",
        start_ts=start,
        duration_s=600.0,
        severity=1.0,
    )
    msg = _make_base_msg()
    inject_comm_dropout(msg, fault)
    assert apply_fault(msg, fault, start) is None


def test_acceptance_each_fault_type_produces_signature_over_1h() -> None:
    """Acceptance test: Each fault type produces its signature over a 1-hour simulated window."""
    sim_start = datetime(2026, 6, 1, 12, 0, 0, tzinfo=UTC)
    clock = FakeClock(initial_time=sim_start)

    fleet: list[DeviceProfile] = make_fleet(4, seed=42)
    # Assign one device per fault type
    # INV-01: OVERHEATING (12:10 - 12:40)
    # INV-02: GRID_SAG (12:10 - 12:40)
    # INV-03: RELAY_STUCK (12:10 - 12:40)
    # INV-04: COMM_DROPOUT (12:10 - 12:40)
    fault_start = sim_start + timedelta(minutes=10)
    duration_s = 1800.0  # 30 minutes

    faults = [
        FaultSpec(
            fault_id="FLT-0001",
            fault_type=FaultType.OVERHEATING,
            device_id="INV-01",
            start_ts=fault_start,
            duration_s=duration_s,
            severity=1.0,
        ),
        FaultSpec(
            fault_id="FLT-0002",
            fault_type=FaultType.GRID_SAG,
            device_id="INV-02",
            start_ts=fault_start,
            duration_s=duration_s,
            severity=0.8,
        ),
        FaultSpec(
            fault_id="FLT-0003",
            fault_type=FaultType.RELAY_STUCK,
            device_id="INV-03",
            start_ts=fault_start,
            duration_s=duration_s,
            severity=1.0,
        ),
        FaultSpec(
            fault_id="FLT-0004",
            fault_type=FaultType.COMM_DROPOUT,
            device_id="INV-04",
            start_ts=fault_start,
            duration_s=duration_s,
            severity=1.0,
        ),
    ]

    session = FaultSession(faults, seed=42)
    runner = SimulationRunner(
        fleet=fleet,
        clock=clock,
        publisher=None,
        seed=42,
        tick_interval_s=15.0,
        fault_hook=session,
    )

    collected: dict[str, list[TelemetryMessage]] = {p.device_id: [] for p in fleet}

    def record_msg(m: TelemetryMessage) -> None:
        collected[m.device_id].append(m)

    # Run for 1 hour (3600s) = 240 steps
    runner.run_simulation(duration_s=3600.0, on_message=record_msg)

    # 1. Overheating signature check (INV-01)
    inv1_msgs = collected["INV-01"]
    assert len(inv1_msgs) == 240
    # Before fault (first 10 min = 40 ticks), temp should be normal (~45 C to 55 C)
    normal_temp = inv1_msgs[35].temperature_c
    # At fault peak (holding period, e.g. at 12:25 = tick 100), temp should be elevated by ~30 C
    peak_temp = inv1_msgs[100].temperature_c
    assert peak_temp - normal_temp >= 25.0, (
        f"Expected overheating signature (>=25C rise), got {peak_temp - normal_temp}C"
    )

    # 2. Grid sag signature check (INV-02)
    inv2_msgs = collected["INV-02"]
    assert len(inv2_msgs) == 240
    # Before fault: nominal ~230 V
    assert inv2_msgs[20].grid_voltage_v > 220.0
    # During fault (between tick 40 and tick 160): grid voltage in [180, 205]
    during_sag = [m.grid_voltage_v for m in inv2_msgs[50:150]]
    assert all(180.0 <= v <= 205.0 for v in during_sag), (
        "Expected grid sag signature in [180, 205]V"
    )

    # 3. Relay stuck signature check (INV-03)
    inv3_msgs = collected["INV-03"]
    assert len(inv3_msgs) == 240
    # During fault: daylight power > 200W, so relay must be open and status warning
    during_stuck = inv3_msgs[50:150]
    for m in during_stuck:
        assert m.relay_state == "open", f"Expected open relay on INV-03, got {m.relay_state}"
        assert m.status == "warning", f"Expected warning status on INV-03, got {m.status}"

    # 4. Comm dropout signature check (INV-04)
    inv4_msgs = collected["INV-04"]
    # During 30 min fault (120 ticks suppressed), INV-04 should only have 120 messages total!
    assert len(inv4_msgs) == 120, f"Expected 120 messages due to dropout, got {len(inv4_msgs)}"
    # Verify no messages for INV-04 between fault_start and fault_start + duration_s
    fault_end = fault_start + timedelta(seconds=duration_s)
    for m in inv4_msgs:
        assert not (fault_start <= m.ts < fault_end), (
            f"INV-04 published message during comm dropout: {m.ts}"
        )
