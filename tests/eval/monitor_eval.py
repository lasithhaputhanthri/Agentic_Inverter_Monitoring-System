"""Monitor evaluation helper and baseline generator.

Purpose: Evaluates monitor false alarm rates and fault detection performance against ground truth.
Inputs: Fleet profiles, simulation parameters, and injected ground truth scenarios.
Outputs: Evaluation summary metrics written to JSON deliverables under docs/baseline/.
"""

from __future__ import annotations

import json
import statistics
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from backend.common.clock import FakeClock
from backend.common.config import MonitorConfig
from backend.common.schemas import TelemetryMessage
from backend.faults.groundtruth import GroundTruthWriter, read_ground_truth
from backend.faults.injector import FaultSession
from backend.faults.models import FaultType
from backend.faults.scheduler import plan_faults
from backend.monitor.detector import TelemetryMonitor
from backend.monitor.models import Alert, MonitorRule
from simulator.devices import make_fleet
from simulator.runner import SimulationRunner

FAULT_TO_RULE_MAP: dict[FaultType, MonitorRule] = {
    FaultType.OVERHEATING: MonitorRule.TEMP_HIGH_FOR_POWER,
    FaultType.GRID_SAG: MonitorRule.GRID_VOLTAGE_LOW,
    FaultType.RELAY_STUCK: MonitorRule.RELAY_MISMATCH,
    FaultType.COMM_DROPOUT: MonitorRule.DEVICE_SILENT,
}


def evaluate_monitor_false_alarms(
    output_path: Path | str = "docs/baseline/monitor_v1_false_alarms.json",
    devices: int = 20,
    duration_s: float = 86400.0,
    seed: int = 42,
) -> dict[str, Any]:
    """Run a fault-free simulation and record baseline false alarm metrics."""
    fleet = make_fleet(devices, seed=seed)
    start_time = datetime(2026, 6, 1, 0, 0, 0, tzinfo=UTC)
    clock = FakeClock(initial_time=start_time)

    monitor = TelemetryMonitor(
        config=MonitorConfig(),
        known_devices=[d.device_id for d in fleet],
        run_id=f"fault_free_run_{seed}",
        start_time=start_time,
    )

    all_alerts: list[Alert] = []

    def on_msg(m: TelemetryMessage) -> None:
        new_alerts = monitor.update(m, now=clock.now())
        all_alerts.extend(new_alerts)

    runner = SimulationRunner(
        fleet=fleet,
        clock=clock,
        publisher=None,
        seed=seed,
        tick_interval_s=15.0,
    )
    total_messages = runner.run_simulation(duration_s=duration_s, on_message=on_msg)

    # Breakdown by rule
    by_rule = {r.value: 0 for r in MonitorRule}
    for a in all_alerts:
        by_rule[a.rule.value] += 1

    days = duration_s / 86400.0
    device_days = devices * days
    alerts_per_device_day = len(all_alerts) / max(0.001, device_days)

    metrics = {
        "run_id": f"fault_free_run_{seed}",
        "simulated_duration_hours": round(duration_s / 3600.0, 1),
        "fleet_devices": devices,
        "device_days": device_days,
        "total_telemetry_messages": total_messages,
        "total_alerts": len(all_alerts),
        "alerts_per_device_day": round(alerts_per_device_day, 4),
        "alerts_by_rule": by_rule,
        "status": "PASS" if alerts_per_device_day == 0.0 else "WARNING",
    }

    out_file = Path(output_path)
    out_file.parent.mkdir(parents=True, exist_ok=True)
    out_file.write_text(json.dumps(metrics, indent=2) + "\n", encoding="utf-8")

    return metrics


def evaluate_monitor_detection(
    output_path: Path | str = "docs/baseline/monitor_v1_detection.json",
    gt_dir: Path | str = "data/raw/ground_truth",
    devices: int = 20,
    duration_s: float = 172800.0,  # 48 hours
    count_per_type: int = 10,  # 40 faults total
    seed: int = 42,
) -> dict[str, Any]:
    """Run a faulted simulation and measure detection rate and latency against ground truth."""
    fleet = make_fleet(devices, seed=seed)
    start_time = datetime(2026, 6, 1, 0, 0, 0, tzinfo=UTC)
    end_time = start_time + timedelta(seconds=duration_s)
    clock = FakeClock(initial_time=start_time)

    # 1. Plan faults
    faults = plan_faults(
        fleet=fleet,
        seed=seed,
        start=start_time,
        end=end_time,
        count_per_type=count_per_type,
    )

    run_id = f"detection_eval_{seed}"
    writer = GroundTruthWriter(run_id=run_id, base_dir=gt_dir)
    session = FaultSession(faults, seed=seed, on_fault_injected=writer.record_fault)

    monitor = TelemetryMonitor(
        config=MonitorConfig(),
        known_devices=[d.device_id for d in fleet],
        run_id=run_id,
        start_time=start_time,
    )

    all_alerts: list[Alert] = []

    def on_msg(m: TelemetryMessage) -> None:
        new_alerts = monitor.update(m, now=clock.now())
        all_alerts.extend(new_alerts)

    runner = SimulationRunner(
        fleet=fleet,
        clock=clock,
        publisher=None,
        seed=seed,
        tick_interval_s=15.0,
        fault_hook=session,
    )
    runner.run_simulation(duration_s=duration_s, on_message=on_msg)

    # 2. Read back ground truth
    gt_records = read_ground_truth(run_id=run_id, base_dir=gt_dir)

    # 3. Match alerts to ground-truth records
    # Group alerts by device_id
    alerts_by_device: dict[str, list[Alert]] = {d.device_id: [] for d in fleet}
    for a in all_alerts:
        alerts_by_device[a.device_id].append(a)

    stats_by_type: dict[str, dict[str, Any]] = {}
    checkpoint_passed = True

    for ft in FaultType:
        expected_rule = FAULT_TO_RULE_MAP[ft]
        type_faults = [f for f in gt_records if f.fault_type == ft]
        detected = 0
        latencies: list[float] = []

        for f in type_faults:
            f_end = f.start_ts + timedelta(seconds=f.duration_s + 120.0)
            dev_alerts = alerts_by_device.get(f.device_id, [])
            matching = [
                a for a in dev_alerts if a.rule == expected_rule and f.start_ts <= a.ts <= f_end
            ]
            if matching:
                detected += 1
                latencies.append((matching[0].ts - f.start_ts).total_seconds())

        total = len(type_faults)
        rate = (detected / total) if total > 0 else 0.0
        med_lat = statistics.median(latencies) if latencies else 0.0

        if rate < 0.80:
            checkpoint_passed = False

        stats_by_type[ft.value] = {
            "injected": total,
            "detected": detected,
            "detection_rate": round(rate, 4),
            "median_latency_seconds": round(med_lat, 1),
            "expected_rule": expected_rule.value,
            "meets_80pct_checkpoint": rate >= 0.80,
        }

    total_injected = sum(s["injected"] for s in stats_by_type.values())
    total_detected = sum(s["detected"] for s in stats_by_type.values())
    overall_rate = total_detected / max(1, total_injected)

    metrics = {
        "run_id": run_id,
        "simulated_duration_hours": round(duration_s / 3600.0, 1),
        "fleet_devices": devices,
        "total_injected_faults": total_injected,
        "total_detected_faults": total_detected,
        "overall_detection_rate": round(overall_rate, 4),
        "by_fault_type": stats_by_type,
        "checkpoint_all_types_ge_80pct": checkpoint_passed,
    }

    out_file = Path(output_path)
    out_file.parent.mkdir(parents=True, exist_ok=True)
    out_file.write_text(json.dumps(metrics, indent=2) + "\n", encoding="utf-8")

    return metrics
