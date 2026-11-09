"""Unit tests for the telemetry message generator.

Purpose: Verifies 1000-message validation, day/night relay behavior, and absence of system clock calls.
Inputs: Synthetic timestamps and device profiles.
Outputs: Assertion checks on generator outputs and source code AST.
"""

from __future__ import annotations

import ast
import inspect
import random
from datetime import UTC, datetime
from pathlib import Path

from iir.common.schemas import TelemetryMessage
from iir.simulator import generator
from iir.simulator.devices import make_fleet
from iir.simulator.generator import next_telemetry


def test_generator_validates_1000_messages() -> None:
    """1000 generated messages all validate against the TelemetryMessage schema."""
    fleet = make_fleet(20, seed=42)
    rng = random.Random(1337)
    base_time = datetime(2026, 6, 1, 6, 0, 0, tzinfo=UTC)

    for i in range(1000):
        profile = fleet[i % len(fleet)]
        # Advance by 15-second simulated intervals
        ts = base_time.replace(
            minute=(i * 15 // 60) % 60,
            hour=6 + ((i * 15 // 3600) % 12),
        )
        msg = next_telemetry(profile, state=None, ts=ts, rng=rng)
        assert isinstance(msg, TelemetryMessage)
        assert msg.status == "normal"
        assert 0.0 <= msg.ac_power_w <= 10000.0


def test_generator_relay_state_day_and_night() -> None:
    """Relay is closed in daylight and open at night."""
    profile = make_fleet(1, seed=42)[0]
    rng = random.Random(42)

    # Noon (12:00) -> Daylight -> relay closed
    noon_time = datetime(2026, 6, 1, 12, 0, 0, tzinfo=UTC)
    msg_noon = next_telemetry(profile, state=None, ts=noon_time, rng=rng)
    assert msg_noon.relay_state == "closed"
    assert msg_noon.ac_power_w > 0.0

    # Midnight (00:00) -> Night -> relay open, power 0
    midnight_time = datetime(2026, 6, 1, 0, 0, 0, tzinfo=UTC)
    msg_night = next_telemetry(profile, state=None, ts=midnight_time, rng=rng)
    assert msg_night.relay_state == "open"
    assert msg_night.ac_power_w == 0.0


def test_generator_contains_no_system_clock_calls() -> None:
    """The generator contains no call to the system clock. Check with a test that inspects the source."""
    source_file = Path(inspect.getfile(generator))
    tree = ast.parse(source_file.read_text(encoding="utf-8"))

    forbidden_names = {"datetime.now", "time.time", "SystemClock", "now"}

    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func_name = ""
            if isinstance(node.func, ast.Attribute):
                if isinstance(node.func.value, ast.Name):
                    func_name = f"{node.func.value.id}.{node.func.attr}"
                else:
                    func_name = node.func.attr
            elif isinstance(node.func, ast.Name):
                func_name = node.func.id

            assert func_name not in forbidden_names, (
                f"Forbidden system clock call detected in generator: {func_name} at line {node.lineno}"
            )
