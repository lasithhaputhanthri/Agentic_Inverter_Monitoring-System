"""Telemetry recording and replay utilities.

Purpose: Records reproducible simulation runs to JSONL and provides offline replay streams.
Inputs: Seed, duration, or saved JSONL file paths.
Outputs: Generated JSONL runs and streamed TelemetryMessage instances.
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

from backend.common.clock import FakeClock
from backend.common.schemas import TelemetryMessage

from simulator.devices import make_fleet
from simulator.runner import DEFAULT_TICK_INTERVAL_S, SimulationRunner


def compute_file_sha256(path: Path | str) -> str:
    """Compute SHA-256 hash of a file without printing or leaking contents."""
    hasher = hashlib.sha256()
    with Path(path).open("rb") as f:
        while chunk := f.read(65536):
            hasher.update(chunk)
    return hasher.hexdigest()


def write_simulation_run(
    seed: int = 42,
    duration_s: float = 86400.0,
    output_path: Path | str | None = None,
    devices: int = 20,
) -> Path:
    """Record a simulated run to a JSONL file.

    Args:
        seed: Random seed for fleet and noise generation.
        duration_s: Simulated duration in seconds (default 86400 = 24 hours).
        output_path: Optional custom destination file.
        devices: Number of inverters in the fleet.

    Returns:
        Path to the recorded JSONL file.
    """
    dest = Path(output_path) if output_path else Path(f"data/raw/sim/run_{seed}.jsonl")
    dest.parent.mkdir(parents=True, exist_ok=True)

    fleet = make_fleet(devices, seed=seed)
    initial_time = datetime(2026, 1, 1, 0, 0, 0, tzinfo=UTC)
    clock = FakeClock(initial_time)
    runner = SimulationRunner(
        fleet=fleet,
        clock=clock,
        publisher=None,
        seed=seed,
        tick_interval_s=DEFAULT_TICK_INTERVAL_S,
    )

    with dest.open("w", encoding="utf-8") as out:

        def save_msg(msg: TelemetryMessage) -> None:
            out.write(msg.model_dump_json() + "\n")

        runner.run_simulation(duration_s=duration_s, on_message=save_msg)

    return dest


def replay_telemetry(file_path: Path | str) -> Iterator[TelemetryMessage]:
    """Stream TelemetryMessage objects from a saved JSONL simulation run.

    Args:
        file_path: Path to the recorded JSONL file.

    Yields:
        Validated TelemetryMessage instances.
    """
    path = Path(file_path)
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            stripped = line.strip()
            if stripped:
                yield TelemetryMessage.model_validate_json(stripped)
