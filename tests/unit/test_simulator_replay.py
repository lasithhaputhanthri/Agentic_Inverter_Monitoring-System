"""Unit tests for JSONL simulation replay.

Purpose: Verifies byte-identical determinism and integrity of saved simulation runs.
Inputs: Temporary JSONL run files and seed parameters.
Outputs: SHA-256 comparison and message deserialization assertions.
"""

from __future__ import annotations

from pathlib import Path

from simulator.replay import compute_file_sha256, replay_telemetry, write_simulation_run


def test_replay_byte_identical_reproducibility(tmp_path: Path) -> None:
    """Replay: the same seed gives a byte-identical JSONL file."""
    run1_path = tmp_path / "run_seed42_a.jsonl"
    run2_path = tmp_path / "run_seed42_b.jsonl"

    # Simulate 1 hour (240 ticks * 20 devices = 4800 messages)
    duration_s = 3600.0

    write_simulation_run(seed=42, duration_s=duration_s, output_path=run1_path, devices=20)
    write_simulation_run(seed=42, duration_s=duration_s, output_path=run2_path, devices=20)

    hash1 = compute_file_sha256(run1_path)
    hash2 = compute_file_sha256(run2_path)

    assert hash1 == hash2, f"Hashes differed: {hash1} vs {hash2}"
    assert run1_path.read_bytes() == run2_path.read_bytes()


def test_replay_messages_validate(tmp_path: Path) -> None:
    """All replayed lines deserialize into valid TelemetryMessage objects."""
    run_path = tmp_path / "sample_run.jsonl"
    write_simulation_run(seed=42, duration_s=300.0, output_path=run_path, devices=5)

    messages = list(replay_telemetry(run_path))
    assert len(messages) == (300 // 15) * 5
    for msg in messages:
        assert msg.device_id.startswith("INV-")
        assert msg.status == "normal"
