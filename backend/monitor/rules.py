"""Pure monitoring rule evaluation functions.

Purpose: Evaluates telemetry windows against deterministic operational thresholds.
Inputs: Sequences of TelemetryMessage readings, timestamps, and threshold limits.
Outputs: Evaluation outcomes specifying whether alerts should be triggered.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime

from backend.common.schemas import TelemetryMessage
from backend.monitor.baseline_model import calculate_expected_temperature


def evaluate_temp_high_for_power(
    readings: Sequence[TelemetryMessage],
    threshold_delta_c: float,
    consecutive_readings: int,
    ambient_c: float = 25.0,
    rated_power_w: float = 5000.0,
) -> tuple[bool, float, float]:
    """Check if temperature minus expected exceeds threshold for consecutive readings.

    Returns:
        Tuple of (triggered: bool, observed_temp_c: float, threshold_delta_c: float).
    """
    if len(readings) < consecutive_readings:
        return False, 0.0, threshold_delta_c

    window = readings[-consecutive_readings:]
    for m in window:
        expected = calculate_expected_temperature(m.ac_power_w, ambient_c, rated_power_w)
        delta = m.temperature_c - expected
        if delta <= threshold_delta_c:
            return False, round(window[-1].temperature_c, 1), threshold_delta_c

    return True, round(window[-1].temperature_c, 1), threshold_delta_c


def evaluate_grid_voltage_low(
    readings: Sequence[TelemetryMessage],
    threshold_v: float,
    consecutive_readings: int,
) -> tuple[bool, float, float]:
    """Check if grid voltage is below allowable threshold for consecutive readings.

    Returns:
        Tuple of (triggered: bool, observed_voltage_v: float, threshold_v: float).
    """
    if len(readings) < consecutive_readings:
        return False, 0.0, threshold_v

    window = readings[-consecutive_readings:]
    for m in window:
        if m.grid_voltage_v >= threshold_v:
            return False, round(window[-1].grid_voltage_v, 1), threshold_v

    return True, round(window[-1].grid_voltage_v, 1), threshold_v


def evaluate_relay_mismatch(
    readings: Sequence[TelemetryMessage],
    power_threshold_w: float,
    consecutive_readings: int,
) -> tuple[bool, str, float]:
    """Check if relay is reported 'open' while active power exceeds threshold for consecutive readings.

    Returns:
        Tuple of (triggered: bool, observed_state: str, threshold_power_w: float).
    """
    if len(readings) < consecutive_readings:
        return False, "normal", power_threshold_w

    window = readings[-consecutive_readings:]
    for m in window:
        if not (m.relay_state == "open" and m.ac_power_w > power_threshold_w):
            return False, m.relay_state, power_threshold_w

    return True, f"open ({window[-1].ac_power_w:.1f}W)", power_threshold_w


def evaluate_device_silent(
    last_seen_ts: datetime | None,
    current_ts: datetime,
    timeout_s: float,
) -> tuple[bool, float, float]:
    """Check if a device has ceased transmitting telemetry past the silence timeout.

    Returns:
        Tuple of (triggered: bool, elapsed_seconds: float, timeout_seconds: float).
    """
    if last_seen_ts is None:
        return False, 0.0, timeout_s

    elapsed_s = max(0.0, (current_ts - last_seen_ts).total_seconds())
    if elapsed_s > timeout_s:
        return True, round(elapsed_s, 1), timeout_s

    return False, round(elapsed_s, 1), timeout_s
