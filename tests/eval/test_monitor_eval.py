"""Evaluation tests for monitor detection rate and false alarms.

Purpose: Verifies the monitor against the 80% detection checkpoint and measures false alarms.
Inputs: Baseline evaluation scripts and ground truth fault scenarios.
Outputs: Pytest assertions and generated JSON deliverables under docs/baseline/.
"""

from __future__ import annotations

from pathlib import Path

from tests.eval.monitor_eval import evaluate_monitor_detection, evaluate_monitor_false_alarms


def test_monitor_false_alarm_baseline() -> None:
    """Evaluate 24-hour fault-free run and generate docs/baseline/monitor_v1_false_alarms.json."""
    output_path = Path("docs/baseline/monitor_v1_false_alarms.json")
    metrics = evaluate_monitor_false_alarms(
        output_path=output_path, devices=20, duration_s=86400.0, seed=42
    )

    assert output_path.exists()
    assert metrics["total_telemetry_messages"] == 115200
    # In a clean nominal run, false alarms should be 0 or exceptionally low
    assert metrics["alerts_per_device_day"] <= 0.1, (
        f"False alarm rate too high: {metrics['alerts_per_device_day']} alerts/device-day"
    )


def test_monitor_detection_baseline_checkpoint() -> None:
    """Evaluate faulted run and verify all fault types exceed the mandatory 80% detection checkpoint."""
    output_path = Path("docs/baseline/monitor_v1_detection.json")
    metrics = evaluate_monitor_detection(
        output_path=output_path,
        devices=20,
        duration_s=172800.0,  # 48 hours
        count_per_type=10,  # 40 faults total
        seed=42,
    )

    assert output_path.exists()
    assert metrics["total_injected_faults"] == 40

    # Verify CHECKPOINT: Each fault type must be detected in >= 80% of injections
    for ft, stats in metrics["by_fault_type"].items():
        rate = stats["detection_rate"]
        assert rate >= 0.80, (
            f"CHECKPOINT FAILURE: Fault type '{ft}' detection rate is {rate * 100:.1f}%, "
            f"below mandatory 80% threshold!"
        )
        assert stats["meets_80pct_checkpoint"] is True

    assert metrics["checkpoint_all_types_ge_80pct"] is True
