"""Unit tests for the simulation runner.

Purpose: Verifies 24-hour deterministic time-stepping across the 20-device fleet.
Inputs: Fleet profiles and FakeClock.
Outputs: Exact count of generated telemetry frames.
"""

from __future__ import annotations

from datetime import UTC, datetime

from iir.common.clock import FakeClock
from iir.simulator.devices import make_fleet
from iir.simulator.runner import DEFAULT_TICK_INTERVAL_S, SimulationRunner


def test_24_hour_run_message_count() -> None:
    """Runner: a 24-hour simulated run with FakeClock produces 20 times 5760 messages."""
    fleet = make_fleet(20, seed=42)
    start_time = datetime(2026, 6, 1, 0, 0, 0, tzinfo=UTC)
    clock = FakeClock(start_time)

    runner = SimulationRunner(
        fleet=fleet,
        clock=clock,
        publisher=None,
        seed=42,
        tick_interval_s=DEFAULT_TICK_INTERVAL_S,
    )

    duration_24h_s = 24.0 * 3600.0  # 86400 seconds
    expected_ticks = int(duration_24h_s / DEFAULT_TICK_INTERVAL_S)  # 5760 ticks
    expected_total_messages = 20 * expected_ticks  # 115200 messages

    count = runner.run_simulation(duration_s=duration_24h_s)
    assert count == expected_total_messages
    assert count == 20 * 5760
