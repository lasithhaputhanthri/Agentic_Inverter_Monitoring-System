"""Physical solar irradiance and inverter behavior curves.

Purpose: Pure mathematical functions modeling daily solar irradiance, power, and thermal dynamics.
Inputs: Hour of day, device hardware profiles, ambient temperature.
Outputs: Normalized irradiance factor, expected AC power in Watts, expected temperature in Celsius.
"""

from __future__ import annotations

import math

from iir.simulator.devices import DeviceProfile

SUNRISE_HOUR: float = 6.0
SUNSET_HOUR: float = 19.0
PEAK_HOUR: float = 12.5
DAY_LENGTH_HOURS: float = SUNSET_HOUR - SUNRISE_HOUR  # 13.0 hours
MAX_NORMAL_TEMP_C: float = 85.0
TEMP_RISE_COEFFICIENT: float = 35.0


def irradiance_factor(local_hour: float) -> float:
    """Calculate normalized solar irradiance factor [0.0, 1.0] for a given hour.

    Rises smoothly from 6:00, peaks at 1.0 near 12:30, and returns to 0.0 at night.

    Args:
        local_hour: Hour of the day as a float (0.0 to 24.0).

    Returns:
        Normalized irradiance factor between 0.0 and 1.0.
    """
    if local_hour <= SUNRISE_HOUR or local_hour >= SUNSET_HOUR:
        return 0.0

    # Symmetric half-sine curve between 6.0 and 19.0 peaking at 12.5
    fraction = (local_hour - SUNRISE_HOUR) / DAY_LENGTH_HOURS
    factor = math.sin(math.pi * fraction)
    return max(0.0, min(1.0, factor))


def expected_power(profile: DeviceProfile, hour: float) -> float:
    """Calculate expected nominal AC power in Watts for an inverter.

    Args:
        profile: Inverter hardware profile.
        hour: Hour of the day (0.0 to 24.0).

    Returns:
        Expected AC output power in Watts.
    """
    factor = irradiance_factor(hour)
    raw_power = profile.rated_power_w * factor
    return round(max(0.0, min(profile.rated_power_w, raw_power)), 1)


def expected_temperature(
    power_w: float,
    ambient_c: float,
    rated_power_w: float = 5000.0,
) -> float:
    """Calculate expected inverter temperature in Celsius based on current power output.

    Thermal dissipation creates a temperature rise proportional to power, capped safely.

    Args:
        power_w: Current power output in Watts.
        ambient_c: Ambient site temperature in Celsius.
        rated_power_w: Inverter rated maximum power in Watts.

    Returns:
        Expected temperature in Celsius, capped below critical limits.
    """
    load_ratio = max(0.0, power_w / max(1.0, rated_power_w))
    temp = ambient_c + (TEMP_RISE_COEFFICIENT * load_ratio)
    return round(min(MAX_NORMAL_TEMP_C, max(-40.0, temp)), 1)
