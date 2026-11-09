"""Unit and integration tests for ground truth logging and replay matching.

Purpose: Validates append-only semantics, persistence integrity, and replay signature matching.
Inputs: Temporary file paths, FaultSpec scenarios, and simulated telemetry streams.
Outputs: Pytest assertions verifying ground-truth audit accuracy.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

from backend.common.clock import FakeClock
from backend.common.schemas import TelemetryMessage
from backend.faults.groundtruth import GroundTruthWriter, read_ground_truth, read_ground_truth_file
from backend.faults.injector import FaultSession
from backend.faults.models import FaultSpec, FaultType
from simulator.devices import make_fleet
from simulator.replay import SimulationRecorder, read_simulation_replay
from simulator.runner import SimulationRunner


def test_ground_truth_writer_append_only(tmp_path: Path) -> None:
    """Acceptance test: The writer appends and never rewrites a line (write twice, read back)."""
    run_id = "test_run_append"
    writer = GroundTruthWriter(run_id=run_id, base_dir=tmp_path)
    file_path = tmp_path / f"{run_id}.jsonl"

    start = datetime(2026, 6, 1, 12, 0, 0, tzinfo=UTC)
    fault1 = FaultSpec(
        fault_id="FLT-0001",
        fault_type=FaultType.OVERHEATING,
        device_id="INV-01",
        start_ts=start,
        duration_s=600.0,
        severity=0.8,
    )
    fault2 = FaultSpec(
        fault_id="FLT-0002",
        fault_type=FaultType.GRID_SAG,
        device_id="INV-02",
        start_ts=start + timedelta(minutes=15),
        duration_s=900.0,
        severity=0.5,
    )

    # First write
    rec1 = writer.record_fault(fault1, injected_at=start)
    assert file_path.exists()

    records_first_read = read_ground_truth(run_id=run_id, base_dir=tmp_path)
    assert len(records_first_read) == 1
    assert records_first_read[0].fault_id == "FLT-0001"

    # Second write using a new writer instance for the same run_id (must append, not overwrite)
    writer2 = GroundTruthWriter(run_id=run_id, base_dir=tmp_path)
    rec2 = writer2.record_fault(fault2, injected_at=start + timedelta(minutes=15))

    records_second_read = read_ground_truth(run_id=run_id, base_dir=tmp_path)
    assert len(records_second_read) == 2, "Expected 2 records after second append"
    assert records_second_read[0].fault_id == rec1.fault_id
    assert records_second_read[1].fault_id == rec2.fault_id


def test_ground_truth_record_matches_replay_signature(tmp_path: Path) -> None:
    """Acceptance test: Every ground-truth record matches a signature in the replay file."""
    run_id = "replay_match_run"
    gt_dir = tmp_path / "ground_truth"
    replay_file = tmp_path / "replay.jsonl"

    start_time = datetime(2026, 6, 1, 12, 0, 0, tzinfo=UTC)
    clock = FakeClock(initial_time=start_time)
    fleet = make_fleet(4, seed=42)

    fault_start = start_time + timedelta(minutes=10)
    duration_s = 1200.0  # 20 minutes

    faults = [
        FaultSpec(
            fault_id="FLT-0001",
            fault_type=FaultType.OVERHEATING,
            device_id="INV-01",
            start_ts=fault_start,
            duration_s=duration_s,
            severity=1.0,
        ),
        FaultSpec(
            fault_id="FLT-0002",
            fault_type=FaultType.GRID_SAG,
            device_id="INV-02",
            start_ts=fault_start,
            duration_s=duration_s,
            severity=0.8,
        ),
        FaultSpec(
            fault_id="FLT-0003",
            fault_type=FaultType.RELAY_STUCK,
            device_id="INV-03",
            start_ts=fault_start,
            duration_s=duration_s,
            severity=1.0,
        ),
        FaultSpec(
            fault_id="FLT-0004",
            fault_type=FaultType.COMM_DROPOUT,
            device_id="INV-04",
            start_ts=fault_start,
            duration_s=duration_s,
            severity=1.0,
        ),
    ]

    writer = GroundTruthWriter(run_id=run_id, base_dir=gt_dir)
    session = FaultSession(faults, seed=42, on_fault_injected=writer.record_fault)

    runner = SimulationRunner(
        fleet=fleet,
        clock=clock,
        publisher=None,
        seed=42,
        tick_interval_s=15.0,
        fault_hook=session,
    )

    # Run simulation recording to replay file
    with SimulationRecorder(replay_file) as recorder:
        runner.run_simulation(duration_s=2400.0, on_message=recorder.record)

    # 1. Read ground truth records
    gt_records = read_ground_truth(run_id=run_id, base_dir=gt_dir)
    assert len(gt_records) == 4

    # 2. Read replay telemetry
    replay_msgs = list(read_simulation_replay(replay_file))
    assert len(replay_msgs) > 0

    # Index replay messages by device_id
    msgs_by_dev: dict[str, list[TelemetryMessage]] = {d.device_id: [] for d in fleet}
    for m in replay_msgs:
        msgs_by_dev[m.device_id].append(m)

    # 3. Verify each ground-truth record matches its observed replay signature
    for record in gt_records:
        dev_msgs = msgs_by_dev[record.device_id]
        f_start = record.start_ts
        f_end = record.start_ts + timedelta(seconds=record.duration_s)

        fault_window_msgs = [m for m in dev_msgs if f_start <= m.ts < f_end]

        if record.fault_type == FaultType.COMM_DROPOUT:
            # During comm dropout, no messages should exist in the replay
            assert len(fault_window_msgs) == 0, (
                f"Found {len(fault_window_msgs)} messages for {record.device_id} during comm dropout"
            )

        elif record.fault_type == FaultType.OVERHEATING:
            # During holding period (e.g. after 5 min of ramp), temp must be elevated
            holding_msgs = [m for m in fault_window_msgs if m.ts >= f_start + timedelta(minutes=5)]
            assert len(holding_msgs) > 0
            # Check elevated temperature
            assert all(m.temperature_c > 65.0 for m in holding_msgs), (
                "Expected elevated temperature in replay during overheating fault"
            )

        elif record.fault_type == FaultType.GRID_SAG:
            assert len(fault_window_msgs) > 0
            assert all(180.0 <= m.grid_voltage_v <= 205.0 for m in fault_window_msgs), (
                "Expected sagged voltage in replay during grid sag fault"
            )

        elif record.fault_type == FaultType.RELAY_STUCK:
            assert len(fault_window_msgs) > 0
            assert all(m.relay_state == "open" for m in fault_window_msgs), (
                "Expected open relay in replay during relay stuck fault"
            )
            assert all(m.status == "warning" for m in fault_window_msgs), (
                "Expected warning status in replay during relay stuck fault"
            )


def test_read_ground_truth_file_missing_file() -> None:
    """Ensure read_ground_truth_file returns empty list if file does not exist."""
    assert read_ground_truth_file(Path("non_existent_file.jsonl")) == []
