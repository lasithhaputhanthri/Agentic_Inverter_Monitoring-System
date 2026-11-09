"""Unit tests for device profiles and fleet generator.

Purpose: Verifies fleet sizing, ID formatting, hardware ranges, and seed reproducibility.
Inputs: Fleet counts and random seeds.
Outputs: Assertion checks on generated fleet profiles.
"""

from __future__ import annotations

import re

from simulator.devices import make_fleet


def test_make_fleet_uniqueness_and_reproducibility() -> None:
    """Fleet produces 20 unique IDs; same seed gives same fleet, different seed gives different."""
    fleet_a = make_fleet(20, seed=42)
    assert len(fleet_a) == 20

    # 20 unique IDs matching ^INV-\d{2}$
    device_ids = [p.device_id for p in fleet_a]
    assert len(set(device_ids)) == 20
    for dev_id in device_ids:
        assert re.match(r"^INV-\d{2}$", dev_id)

    # Identical fleet with identical seed
    fleet_b = make_fleet(20, seed=42)
    assert fleet_a == fleet_b

    # Different seed gives different fleet
    fleet_c = make_fleet(20, seed=99)
    assert fleet_a != fleet_c


def test_device_profile_bounds() -> None:
    """Hardware parameters fall within realistic physical ranges."""
    fleet = make_fleet(20, seed=123)
    for profile in fleet:
        assert 2000.0 <= profile.rated_power_w <= 6000.0
        assert 8 <= profile.panel_count <= 24
        assert -3.0 <= profile.ambient_offset_c <= 3.0
