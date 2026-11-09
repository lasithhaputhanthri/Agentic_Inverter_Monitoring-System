"""Unit tests for solar irradiance and physical curves.

Purpose: Verifies mathematical properties of daily irradiance and power curves.
Inputs: Hour intervals and device profile.
Outputs: Assertion checks on curve continuity, peaks, and monotonic rise/fall.
"""

from __future__ import annotations

from simulator.curves import irradiance_factor


def test_irradiance_factor_night_and_peak() -> None:
    """irradiance_factor(0) == 0 and irradiance_factor(12.5) is within 0.01 of 1.0."""
    assert irradiance_factor(0.0) == 0.0
    assert irradiance_factor(5.9) == 0.0
    assert irradiance_factor(19.1) == 0.0
    assert irradiance_factor(23.5) == 0.0

    peak = irradiance_factor(12.5)
    assert abs(peak - 1.0) <= 0.01


def test_irradiance_factor_rises_and_falls() -> None:
    """The curve rises from 6:00 to 12:30 and falls afterwards."""
    # Test strictly increasing from 6:00 to 12:30
    hours_morning = [6.0 + 0.5 * i for i in range(14)]  # 6.0 to 12.5
    values_morning = [irradiance_factor(h) for h in hours_morning]
    for i in range(len(values_morning) - 1):
        assert values_morning[i] < values_morning[i + 1]

    # Test strictly decreasing from 12:30 to 19:00
    hours_afternoon = [12.5 + 0.5 * i for i in range(14)]  # 12.5 to 19.0
    values_afternoon = [irradiance_factor(h) for h in hours_afternoon]
    for i in range(len(values_afternoon) - 1):
        assert values_afternoon[i] > values_afternoon[i + 1]
