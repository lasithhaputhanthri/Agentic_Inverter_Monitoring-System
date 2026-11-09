"""Unit tests for the monitor baseline thermal model.

Purpose: Verifies the monitor's independent thermal model matches the simulator within 0.5 degrees
         across a comprehensive grid of operating conditions.
Inputs: Grid of active power values (0 to 6000 W) and ambient temperatures (-20 to 50 C).
Outputs: Pytest assertions verifying mathematical consistency.
"""

from __future__ import annotations

from backend.monitor.baseline_model import (
    MAX_NORMAL_TEMP_C,
    calculate_expected_temperature,
)
from simulator.curves import expected_temperature as sim_expected_temperature


def test_monitor_baseline_matches_simulator_within_half_degree() -> None:
    """Acceptance test: Baseline model and simulator expected temperature agree within 0.5 degrees."""
    power_grid = [0.0, 500.0, 1000.0, 2500.0, 4000.0, 5000.0, 6000.0]
    ambient_grid = [-20.0, -5.0, 0.0, 15.0, 25.0, 35.0, 45.0, 50.0]
    rated_power_w = 5000.0

    max_diff = 0.0
    for power in power_grid:
        for ambient in ambient_grid:
            monitor_temp = calculate_expected_temperature(
                power_w=power,
                ambient_c=ambient,
                rated_power_w=rated_power_w,
            )
            sim_temp = sim_expected_temperature(
                power_w=power,
                ambient_c=ambient,
                rated_power_w=rated_power_w,
            )
            diff = abs(monitor_temp - sim_temp)
            if diff > max_diff:
                max_diff = diff
            assert diff <= 0.5, (
                f"Discrepancy too large at power={power}W, ambient={ambient}C: "
                f"monitor={monitor_temp}C, sim={sim_temp}C (diff={diff}C > 0.5C)"
            )

    # In fact, since the mathematical model is identical, max_diff should be 0.0
    assert max_diff <= 0.1


def test_calculate_expected_temperature_clamped_at_max() -> None:
    """Verify that expected temperature does not exceed physical upper clamp."""
    temp = calculate_expected_temperature(power_w=10000.0, ambient_c=70.0)
    assert temp <= MAX_NORMAL_TEMP_C
