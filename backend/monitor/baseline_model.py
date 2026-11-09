"""Baseline physical thermal model for telemetry monitoring.

Purpose: Independent copy of the thermal dissipation model used to detect anomalous inverter heating.
Inputs: Inverter power output in Watts, ambient temperature in Celsius, and rated power.
Outputs: Expected nominal inverter temperature in Celsius.
"""

from __future__ import annotations

MAX_NORMAL_TEMP_C: float = 85.0
TEMP_RISE_COEFFICIENT: float = 35.0
DEFAULT_RATED_POWER_W: float = 5000.0
DEFAULT_AMBIENT_C: float = 25.0


def calculate_expected_temperature(
    power_w: float,
    ambient_c: float = DEFAULT_AMBIENT_C,
    rated_power_w: float = DEFAULT_RATED_POWER_W,
) -> float:
    """Calculate expected nominal inverter temperature in Celsius based on active power.

    Thermal dissipation produces a temperature rise above ambient proportional to the inverter load.

    Args:
        power_w: Current active power generation in Watts.
        ambient_c: Estimated or measured ambient temperature in Celsius.
        rated_power_w: Inverter rated maximum power in Watts.

    Returns:
        Expected operating temperature in Celsius, clamped to physical limits.
    """
    load_ratio = max(0.0, power_w / max(1.0, rated_power_w))
    temp = ambient_c + (TEMP_RISE_COEFFICIENT * load_ratio)
    return round(min(MAX_NORMAL_TEMP_C, max(-40.0, temp)), 1)
