"""Fleet device profiles and generator.

Purpose: Creates reproducible inverter specifications and fleet configurations.
Inputs: Fleet size and pseudo-random seed.
Outputs: List of immutable DeviceProfile instances.
"""

from __future__ import annotations

import random
from dataclasses import dataclass


@dataclass(frozen=True)
class DeviceProfile:
    """Hardware specifications and local physical characteristics for an inverter."""

    device_id: str
    rated_power_w: float
    panel_count: int
    ambient_offset_c: float


def make_fleet(n: int = 20, seed: int = 42) -> list[DeviceProfile]:
    """Generate a fleet of n reproducible device profiles based on a seed.

    Args:
        n: Number of inverter profiles to generate (default 20).
        seed: Random seed guaranteeing reproducibility.

    Returns:
        List of DeviceProfile instances with IDs formatted as INV-01, INV-02, etc.
    """
    rng = random.Random(seed)  # nosec: B311
    profiles: list[DeviceProfile] = []

    for i in range(1, n + 1):
        dev_id = f"INV-{i:02d}"
        rated_power = round(rng.uniform(2000.0, 6000.0), 1)
        panel_count = rng.randint(8, 24)
        ambient_offset = round(rng.uniform(-3.0, 3.0), 2)

        profiles.append(
            DeviceProfile(
                device_id=dev_id,
                rated_power_w=rated_power,
                panel_count=panel_count,
                ambient_offset_c=ambient_offset,
            )
        )

    return profiles
