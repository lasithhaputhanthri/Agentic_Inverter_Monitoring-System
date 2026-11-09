"""Pure telemetry message generator.

Purpose: Synthesizes physical inverter readings with calibrated noise for each time step.
Inputs: Device profile, previous state, timestamp, and seeded random number generator.
Outputs: Validated, immutable TelemetryMessage instance.
"""

from __future__ import annotations

import random
from datetime import datetime
from typing import Any

from backend.common.schemas import RelayState, TelemetryMessage

from simulator.curves import (
    SUNRISE_HOUR,
    SUNSET_HOUR,
    expected_power,
    expected_temperature,
)
from simulator.devices import DeviceProfile

NOMINAL_GRID_VOLTAGE_V: float = 230.0
PANEL_VMP_V: float = 34.0
BASE_AMBIENT_TEMP_C: float = 25.0


def next_telemetry(
    profile: DeviceProfile,
    state: dict[str, Any] | None,
    ts: datetime,
    rng: random.Random,
) -> TelemetryMessage:
    """Generate the next telemetry reading for an inverter profile.

    This is a pure function that never calls the system clock directly.

    Args:
        profile: Inverter hardware specification.
        state: Optional dictionary representing prior step device state.
        ts: Timezone-aware UTC timestamp for the measurement.
        rng: Seeded random number generator for Gaussian perturbation.

    Returns:
        Validated, immutable TelemetryMessage.
    """
    del state  # Reserved for multi-step fault dynamics in future phases

    # Calculate decimal local hour from the timestamp
    hour = ts.hour + (ts.minute / 60.0) + (ts.second / 3600.0)
    is_daylight = SUNRISE_HOUR < hour < SUNSET_HOUR

    # Nominal expected power
    nom_power = expected_power(profile, hour)

    if is_daylight and nom_power > 0.0:
        relay: RelayState = "closed"
        # Seeded Gaussian noise ~ 1% on power
        power_noise = rng.gauss(0.0, 0.01 * nom_power)
        ac_power = round(max(0.0, min(10000.0, nom_power + power_noise)), 1)
        # DC voltage based on panel strings with slight variance
        nominal_dc = profile.panel_count * PANEL_VMP_V
        dc_voltage = round(max(0.0, min(1000.0, nominal_dc + rng.gauss(0.0, 2.0))), 1)
    else:
        relay = "open"
        ac_power = 0.0
        dc_voltage = 0.0

    # Grid voltage centered at 230V with ~1V Gaussian noise
    grid_voltage = round(max(0.0, min(300.0, NOMINAL_GRID_VOLTAGE_V + rng.gauss(0.0, 1.0))), 1)

    # Ambient temperature including device local offset
    ambient_c = BASE_AMBIENT_TEMP_C + profile.ambient_offset_c
    nom_temp = expected_temperature(ac_power, ambient_c, profile.rated_power_w)
    # Small thermal noise ~ 0.2 C
    temp_noise = rng.gauss(0.0, 0.2)
    temperature = round(max(-40.0, min(120.0, nom_temp + temp_noise)), 1)

    return TelemetryMessage(
        device_id=profile.device_id,
        ts=ts,
        ac_power_w=ac_power,
        dc_voltage_v=dc_voltage,
        grid_voltage_v=grid_voltage,
        temperature_c=temperature,
        relay_state=relay,
        status="normal",
    )
