"""Unit tests for pure monitoring rules.

Purpose: Verifies individual rule thresholds, consecutive reading requirements,
         and edge-case behaviors.
Inputs: Synthetic sequences of TelemetryMessage readings and elapsed silence durations.
Outputs: Pytest assertions verifying rule evaluation decisions.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from backend.common.schemas import TelemetryMessage
from backend.monitor.rules import (
    evaluate_device_silent,
    evaluate_grid_voltage_low,
    evaluate_relay_mismatch,
    evaluate_temp_high_for_power,
)


def _msg(
    temp_c: float = 40.0,
    power_w: float = 3000.0,
    grid_v: float = 230.0,
    relay: str = "closed",
    ts: datetime | None = None,
) -> TelemetryMessage:
    return TelemetryMessage(
        device_id="INV-01",
        ts=ts or datetime(2026, 6, 1, 12, 0, 0, tzinfo=UTC),
        ac_power_w=power_w,
        dc_voltage_v=400.0,
        grid_voltage_v=grid_v,
        temperature_c=temp_c,
        relay_state=relay,  # type: ignore[arg-type]
        status="normal",
    )


def test_rule_temp_high_for_power_consecutive_requirement() -> None:
    """Acceptance test: Rule fires on condition, does NOT fire on 1 reading, requires 3 in a row."""
    # At 3000 W and ambient 25 C: expected temp = 25 + 35 * (3000/5000) = 46.0 C
    # Threshold delta is 12.0 C -> anomalous temp is > 58.0 C
    normal = _msg(temp_c=46.0, power_w=3000.0)
    high = _msg(temp_c=65.0, power_w=3000.0)  # delta = +19 C > 12 C

    # 1 reading high: False
    trig, _, _ = evaluate_temp_high_for_power(
        [high], threshold_delta_c=12.0, consecutive_readings=3
    )
    assert trig is False

    # 2 readings high: False
    trig, _, _ = evaluate_temp_high_for_power(
        [high, high], threshold_delta_c=12.0, consecutive_readings=3
    )
    assert trig is False

    # 3 readings high: True
    trig, obs, thresh = evaluate_temp_high_for_power(
        [high, high, high], threshold_delta_c=12.0, consecutive_readings=3
    )
    assert trig is True
    assert obs == 65.0
    assert thresh == 12.0

    # 2 high, 1 normal: False
    trig, _, _ = evaluate_temp_high_for_power(
        [high, high, normal], threshold_delta_c=12.0, consecutive_readings=3
    )
    assert trig is False


def test_rule_grid_voltage_low_consecutive_requirement() -> None:
    """Acceptance test: Grid voltage low requires 3 consecutive readings < 207 V."""
    normal = _msg(grid_v=230.0)
    sag = _msg(grid_v=200.0)

    # 1 reading: False
    trig, _, _ = evaluate_grid_voltage_low([sag], threshold_v=207.0, consecutive_readings=3)
    assert trig is False

    # 2 readings: False
    trig, _, _ = evaluate_grid_voltage_low([sag, sag], threshold_v=207.0, consecutive_readings=3)
    assert trig is False

    # 3 readings: True
    trig, obs, thresh = evaluate_grid_voltage_low(
        [sag, sag, sag], threshold_v=207.0, consecutive_readings=3
    )
    assert trig is True
    assert obs == 200.0
    assert thresh == 207.0

    # 2 sag, 1 normal: False
    trig, _, _ = evaluate_grid_voltage_low(
        [sag, sag, normal], threshold_v=207.0, consecutive_readings=3
    )
    assert trig is False


def test_rule_relay_mismatch_consecutive_requirement() -> None:
    """Acceptance test: Relay mismatch requires 2 consecutive readings open while power > 200 W."""
    closed_power = _msg(power_w=1500.0, relay="closed")
    open_power = _msg(power_w=1500.0, relay="open")
    open_night = _msg(power_w=0.0, relay="open")

    # 1 reading: False
    trig, _, _ = evaluate_relay_mismatch(
        [open_power], power_threshold_w=200.0, consecutive_readings=2
    )
    assert trig is False

    # 2 readings open with power: True
    trig, obs, thresh = evaluate_relay_mismatch(
        [open_power, open_power], power_threshold_w=200.0, consecutive_readings=2
    )
    assert trig is True
    assert "open" in obs
    assert thresh == 200.0

    # Open with zero power (night disconnect): False
    trig, _, _ = evaluate_relay_mismatch(
        [open_night, open_night], power_threshold_w=200.0, consecutive_readings=2
    )
    assert trig is False

    # Closed normal: False
    trig, _, _ = evaluate_relay_mismatch(
        [closed_power, closed_power], power_threshold_w=200.0, consecutive_readings=2
    )
    assert trig is False


def test_rule_device_silent_timeout() -> None:
    """Acceptance test: Device silence rule evaluates elapsed time > 60 seconds."""
    t0 = datetime(2026, 6, 1, 12, 0, 0, tzinfo=UTC)

    # Within 60 seconds: False
    trig, obs, _ = evaluate_device_silent(t0, t0 + timedelta(seconds=45), timeout_s=60.0)
    assert trig is False
    assert obs == 45.0

    # Exactly 60 seconds: False
    trig, obs, _ = evaluate_device_silent(t0, t0 + timedelta(seconds=60), timeout_s=60.0)
    assert trig is False

    # 61 seconds: True
    trig, obs, thresh = evaluate_device_silent(t0, t0 + timedelta(seconds=61), timeout_s=60.0)
    assert trig is True
    assert obs == 61.0
    assert thresh == 60.0

    # Never seen: False
    trig, _, _ = evaluate_device_silent(None, t0, timeout_s=60.0)
    assert trig is False
