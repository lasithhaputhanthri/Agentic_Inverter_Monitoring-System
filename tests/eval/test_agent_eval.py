"""Evaluation test for Phase 4 diagnosis agent baseline deliverable.

Purpose: Verifies the tuning evaluation split generation and baseline metrics recording.
Inputs: Synthetic tuning split fixtures and FakeLLMClient.
Outputs: Pytest assertions on docs/baseline/diagnosis_v1.json metrics.
"""

from __future__ import annotations

import json

from tests.eval.tuning_eval import BASELINE_OUTPUT, HELD_OUT_DIR, TUNING_DIR, run_tuning_evaluation


def test_diagnosis_tuning_evaluation_baseline() -> None:
    """Acceptance test: Tuning evaluation runs, records baseline deliverable, leaves held-out untouched."""
    metrics = run_tuning_evaluation()

    assert BASELINE_OUTPUT.exists(), (
        "Baseline deliverable docs/baseline/diagnosis_v1.json must exist"
    )
    loaded = json.loads(BASELINE_OUTPUT.read_text(encoding="utf-8"))

    assert metrics["total_alerts"] == 100
    assert loaded["total_alerts"] == 100
    assert loaded["accuracy"] == 1.0
    assert loaded["token_usage_per_alert"]["input_tokens_max"] <= 1500
    assert loaded["token_usage_per_alert"]["output_tokens_max"] <= 300
    assert (TUNING_DIR / "alerts.json").exists()
    assert (HELD_OUT_DIR / "alerts.json").exists()
    assert "un-run" in loaded["held_out_status"]
