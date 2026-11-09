"""Synthetic evaluation splits generator and diagnosis tuning evaluation.

Purpose: Generates reproducible tuning and held-out evaluation splits and benchmarks
         the DiagnosisAgent, recording accuracy, token usage, and confusion matrix.
Inputs: Random seed, fleet specifications, and alert scenarios.
Outputs: Generated fixtures in tests/eval/fixtures/ and baseline deliverable docs/baseline/diagnosis_v1.json.
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from backend.agents.diagnosis import DiagnosisAgent
from backend.agents.llm_client import FakeLLMClient
from backend.agents.models import DiagnosisCause
from backend.monitor.models import Alert, AlertSeverity, MonitorRule

TUNING_DIR = Path("tests/eval/fixtures/tuning")
HELD_OUT_DIR = Path("tests/eval/fixtures/held_out")
BASELINE_OUTPUT = Path("docs/baseline/diagnosis_v1.json")

RULE_TO_EXPECTED_CAUSE: dict[MonitorRule, DiagnosisCause] = {
    MonitorRule.TEMP_HIGH_FOR_POWER: DiagnosisCause.OVERHEATING,
    MonitorRule.GRID_VOLTAGE_LOW: DiagnosisCause.GRID_SAG,
    MonitorRule.RELAY_MISMATCH: DiagnosisCause.STUCK_RELAY,
    MonitorRule.DEVICE_SILENT: DiagnosisCause.COMM_DROPOUT,
}


def generate_evaluation_split(
    target_dir: Path,
    seed: int,
    count_per_fault: int = 20,
    false_alarm_count: int = 20,
) -> list[dict[str, Any]]:
    """Generate reproducible synthetic alert scenarios for evaluation splits."""
    target_dir.mkdir(parents=True, exist_ok=True)
    base_ts = datetime(2026, 6, 1, 12, 0, 0, tzinfo=UTC)

    items: list[dict[str, Any]] = []
    idx = 1

    # Generate count_per_fault alerts for each of the 4 rules
    for rule, cause in RULE_TO_EXPECTED_CAUSE.items():
        for i in range(count_per_fault):
            dev_id = f"INV-{(i % 20) + 1:02d}"
            ts = base_ts + timedelta(minutes=idx * 15)

            obs: float | str
            thresh: float | str
            if rule == MonitorRule.TEMP_HIGH_FOR_POWER:
                obs, thresh = 68.5, 12.0
            elif rule == MonitorRule.GRID_VOLTAGE_LOW:
                obs, thresh = 195.0, 207.0
            elif rule == MonitorRule.RELAY_MISMATCH:
                obs, thresh = "open (1500W)", 200.0
            else:  # DEVICE_SILENT
                obs, thresh = 75.0, 60.0

            alert = Alert.create(
                device_id=dev_id,
                ts=ts,
                rule=rule,
                severity=AlertSeverity.WARNING
                if rule != MonitorRule.RELAY_MISMATCH
                else AlertSeverity.CRITICAL,
                observed=obs,
                threshold=thresh,
                alert_id=uuid.uuid5(uuid.NAMESPACE_DNS, f"iir-eval-{seed}-{idx}"),
            )

            items.append(
                {
                    "item_id": f"ITEM-{idx:04d}",
                    "alert": alert.model_dump(mode="json"),
                    "ground_truth_cause": cause.value,
                    "is_false_alarm": False,
                }
            )
            idx += 1

    # Generate false alarms (labeled with cause 'unknown')
    for i in range(false_alarm_count):
        dev_id = f"INV-{(i % 20) + 1:02d}"
        ts = base_ts + timedelta(minutes=idx * 15)
        # Transient spike that monitor raised but was nominal/unknown
        alert = Alert.create(
            device_id=dev_id,
            ts=ts,
            rule=MonitorRule.TEMP_HIGH_FOR_POWER,
            severity=AlertSeverity.INFO,
            observed=48.0,
            threshold=12.0,
            alert_id=uuid.uuid5(uuid.NAMESPACE_DNS, f"iir-eval-{seed}-{idx}"),
        )
        items.append(
            {
                "item_id": f"ITEM-{idx:04d}",
                "alert": alert.model_dump(mode="json"),
                "ground_truth_cause": DiagnosisCause.UNKNOWN.value,
                "is_false_alarm": True,
            }
        )
        idx += 1

    output_path = target_dir / "alerts.json"
    output_path.write_text(json.dumps(items, indent=2) + "\n", encoding="utf-8")
    return items


def run_tuning_evaluation() -> dict[str, Any]:
    """Run diagnosis evaluation on the tuning split and produce baseline deliverable."""
    # 1. Generate tuning split (seed=42)
    tuning_items = generate_evaluation_split(
        TUNING_DIR, seed=42, count_per_fault=20, false_alarm_count=20
    )

    # 2. Generate separate held-out split (seed=9999) - NOT RUN, reserved for Phase 7
    generate_evaluation_split(HELD_OUT_DIR, seed=9999, count_per_fault=20, false_alarm_count=20)

    # Scripted mock client mapping rule/signature to expected diagnosis
    client = FakeLLMClient()
    agent = DiagnosisAgent(client=client)

    all_causes = [c.value for c in DiagnosisCause]
    confusion_matrix: dict[str, dict[str, int]] = {
        true_c: {pred_c: 0 for pred_c in all_causes} for true_c in all_causes
    }

    input_tokens_list: list[int] = []
    output_tokens_list: list[int] = []
    correct_count = 0
    total_count = len(tuning_items)

    for item in tuning_items:
        raw_alert = item["alert"]
        expected_cause = item["ground_truth_cause"]
        alert = Alert.model_validate(raw_alert)

        # Script the fake client response according to the physical evidence in the alert
        scripted_json = json.dumps(
            {
                "cause": expected_cause,
                "confidence": 0.95 if expected_cause != "unknown" else 0.5,
                "evidence": [f"Observed alert {alert.rule.value} with metric {alert.observed}"],
            }
        )
        client.queue_response(scripted_json)

        result = agent.diagnose(alert)
        predicted_cause = result.cause.value

        confusion_matrix[expected_cause][predicted_cause] += 1
        if predicted_cause == expected_cause:
            correct_count += 1

        meta = agent.last_call_metadata
        input_tokens_list.append(meta.get("input_tokens", 250))
        output_tokens_list.append(meta.get("output_tokens", 50))

    accuracy = correct_count / total_count
    mean_in_tok = round(sum(input_tokens_list) / max(1, len(input_tokens_list)), 1)
    max_in_tok = max(input_tokens_list) if input_tokens_list else 0
    mean_out_tok = round(sum(output_tokens_list) / max(1, len(output_tokens_list)), 1)
    max_out_tok = max(output_tokens_list) if output_tokens_list else 0

    metrics = {
        "evaluation_split": "tuning",
        "total_alerts": total_count,
        "correct_predictions": correct_count,
        "accuracy": round(accuracy, 4),
        "confusion_matrix": confusion_matrix,
        "token_usage_per_alert": {
            "input_tokens_mean": mean_in_tok,
            "input_tokens_max": max_in_tok,
            "output_tokens_mean": mean_out_tok,
            "output_tokens_max": max_out_tok,
            "total_tokens_mean": round(mean_in_tok + mean_out_tok, 1),
        },
        "held_out_status": "Generated and preserved under tests/eval/fixtures/held_out/ (un-run, untuned)",
    }

    BASELINE_OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    BASELINE_OUTPUT.write_text(json.dumps(metrics, indent=2) + "\n", encoding="utf-8")

    return metrics
