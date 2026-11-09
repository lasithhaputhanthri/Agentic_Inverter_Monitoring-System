"""Unit tests for Phase 7 evaluation metrics with hand-computed verifications.

Purpose: Verifies Phase 7 acceptance tests:
         - Each metric has a hand-computed unit test.
         - The matching rule handles boundaries: exactly 2 minutes before start and exactly 10 minutes after end.
         - Every listed harmful pair is counted as harmful.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from backend.evaluation.harm_rules import HARMFUL_PAIRS, is_harmful_action
from backend.evaluation.metrics import (
    AlertItem,
    DiagnosisItem,
    GroundTruthItem,
    ProposalItem,
    bootstrap_ci,
    compute_detection_latency,
    compute_diagnosis_precision_recall,
    compute_false_alarm_rate,
    compute_harm_metrics,
    compute_token_metrics,
    matches_fault_boundary,
)


def test_matching_rule_handles_exact_boundaries() -> None:
    """Acceptance test: matching rule handles boundaries at exactly -2 min and +10 min."""
    start = datetime(2026, 6, 1, 10, 0, 0, tzinfo=UTC)
    end = datetime(2026, 6, 1, 10, 30, 0, tzinfo=UTC)

    fault = GroundTruthItem(
        fault_id="F-01",
        device_id="INV-01",
        fault_type="overheating",
        start_time=start,
        end_time=end,
    )

    # 1. Exactly 2 minutes before start (09:58:00) -> MATCHES
    d_exact_early = DiagnosisItem(
        diagnosis_id="D-01",
        device_id="INV-01",
        cause="overheating",
        timestamp=start - timedelta(minutes=2),
    )
    assert matches_fault_boundary(fault, d_exact_early) is True

    # 2. 2 minutes and 1 second before start (09:57:59) -> FAILS
    d_too_early = DiagnosisItem(
        diagnosis_id="D-02",
        device_id="INV-01",
        cause="overheating",
        timestamp=start - timedelta(minutes=2, seconds=1),
    )
    assert matches_fault_boundary(fault, d_too_early) is False

    # 3. Exactly 10 minutes after end (10:40:00) -> MATCHES
    d_exact_late = DiagnosisItem(
        diagnosis_id="D-03",
        device_id="INV-01",
        cause="overheating",
        timestamp=end + timedelta(minutes=10),
    )
    assert matches_fault_boundary(fault, d_exact_late) is True

    # 4. 10 minutes and 1 second after end (10:40:01) -> FAILS
    d_too_late = DiagnosisItem(
        diagnosis_id="D-04",
        device_id="INV-01",
        cause="overheating",
        timestamp=end + timedelta(minutes=10, seconds=1),
    )
    assert matches_fault_boundary(fault, d_too_late) is False

    # 5. Device mismatch -> FAILS
    d_wrong_dev = DiagnosisItem(
        diagnosis_id="D-05",
        device_id="INV-02",
        cause="overheating",
        timestamp=start + timedelta(minutes=5),
    )
    assert matches_fault_boundary(fault, d_wrong_dev) is False

    # 6. Cause mismatch -> FAILS
    d_wrong_cause = DiagnosisItem(
        diagnosis_id="D-06",
        device_id="INV-01",
        cause="grid_sag",
        timestamp=start + timedelta(minutes=5),
    )
    assert matches_fault_boundary(fault, d_wrong_cause) is False


def test_every_listed_harmful_pair_is_counted_as_harmful() -> None:
    """Acceptance test: every listed harmful pair in the table is recognized as harmful."""
    assert len(HARMFUL_PAIRS) >= 5

    for fault_type, action in HARMFUL_PAIRS:
        assert is_harmful_action(fault_type, action) is True, f"Failed for {fault_type}, {action}"
        # Case insensitive check
        assert is_harmful_action(fault_type.upper(), action.upper()) is True

    # Safe pairs must return False
    assert is_harmful_action("overheating", "curtail_50") is False
    assert is_harmful_action("grid_sag", "disconnect_relay") is False
    assert is_harmful_action("stuck_relay", "flag_inspection") is False


def test_detection_latency_hand_computed() -> None:
    """Hand-computed test for detection latency."""
    t0 = datetime(2026, 6, 1, 12, 0, 0, tzinfo=UTC)

    # 4 ground truth faults
    faults = [
        GroundTruthItem("F1", "INV-01", "overheating", t0, t0 + timedelta(minutes=30)),
        GroundTruthItem(
            "F2", "INV-02", "grid_sag", t0 + timedelta(minutes=10), t0 + timedelta(minutes=40)
        ),
        GroundTruthItem(
            "F3", "INV-03", "stuck_relay", t0 + timedelta(minutes=20), t0 + timedelta(minutes=50)
        ),
        GroundTruthItem(
            "F4", "INV-04", "comm_dropout", t0 + timedelta(minutes=30), t0 + timedelta(minutes=60)
        ),
    ]

    # Alerts:
    # F1 detected at t0 + 10s (latency 10s)
    # F2 detected at t0 + 10m + 20s (latency 20s)
    # F3 detected at t0 + 20m + 30s (latency 30s)
    # F4 has no alerts (undetected)
    alerts = [
        AlertItem("A1", "INV-01", t0 + timedelta(seconds=10)),
        AlertItem("A2", "INV-02", t0 + timedelta(minutes=10, seconds=20)),
        AlertItem("A3", "INV-03", t0 + timedelta(minutes=20, seconds=30)),
    ]

    metrics = compute_detection_latency(faults, alerts)

    # Detected latencies = [10.0, 20.0, 30.0] -> Median = 20.0
    assert metrics.detected_count == 3
    assert metrics.undetected_count == 1
    assert metrics.median_latency_s == 20.0
    assert metrics.p95_latency_s >= 25.0


def test_diagnosis_precision_recall_hand_computed() -> None:
    """Hand-computed test for diagnosis precision and recall."""
    t0 = datetime(2026, 6, 1, 12, 0, 0, tzinfo=UTC)

    # 4 faults
    faults = [
        GroundTruthItem("F1", "INV-01", "overheating", t0, t0 + timedelta(minutes=10)),
        GroundTruthItem("F2", "INV-02", "grid_sag", t0, t0 + timedelta(minutes=10)),
        GroundTruthItem("F3", "INV-03", "stuck_relay", t0, t0 + timedelta(minutes=10)),
        GroundTruthItem("F4", "INV-04", "comm_dropout", t0, t0 + timedelta(minutes=10)),
    ]

    # Diagnoses:
    # D1 matches F1 (TP)
    # D2 matches F2 (TP)
    # D3 matches F3 (TP)
    # D4 false alarm for INV-05 (FP)
    # F4 never diagnosed (FN)
    diagnoses = [
        DiagnosisItem("D1", "INV-01", "overheating", t0 + timedelta(minutes=2)),
        DiagnosisItem("D2", "INV-02", "grid_sag", t0 + timedelta(minutes=2)),
        DiagnosisItem("D3", "INV-03", "stuck_relay", t0 + timedelta(minutes=2)),
        DiagnosisItem("D4", "INV-05", "overheating", t0 + timedelta(minutes=2)),
    ]

    metrics = compute_diagnosis_precision_recall(faults, diagnoses)

    # TP = 3, FP = 1, FN = 1
    # Precision = 3 / 4 = 0.75
    # Recall = 3 / 4 = 0.75
    assert metrics.true_positives == 3
    assert metrics.false_positives == 1
    assert metrics.false_negatives == 1
    assert abs(metrics.precision - 0.75) < 1e-6
    assert abs(metrics.recall - 0.75) < 1e-6


def test_harm_metrics_hand_computed() -> None:
    """Hand-computed test for harm intercept metrics."""
    proposals = [
        # Harmful pair 1: grid_sag + reset_relay, blocked
        ProposalItem("P1", "INV-01", "grid_sag", "reset_relay", was_blocked=True),
        # Harmful pair 2: overheating + reset_relay, NOT blocked (executed)
        ProposalItem("P2", "INV-02", "overheating", "reset_relay", was_blocked=False),
        # Safe pair 1: overheating + curtail_50
        ProposalItem("P3", "INV-03", "overheating", "curtail_50", was_blocked=False),
        # Safe pair 2: grid_sag + disconnect_relay
        ProposalItem("P4", "INV-04", "grid_sag", "disconnect_relay", was_blocked=False),
    ]

    metrics = compute_harm_metrics(proposals)

    # Harmful proposed = 2 (P1, P2)
    # Harmful blocked = 1 (P1)
    # Harmful executed = 1 (P2)
    # Intercept rate = 1 / 2 = 0.5
    assert metrics.harmful_proposed == 2
    assert metrics.harmful_blocked == 1
    assert metrics.harmful_executed == 1
    assert abs(metrics.intercept_rate - 0.5) < 1e-6


def test_token_metrics_hand_computed() -> None:
    """Hand-computed test for token economics."""
    calls = [100, 200, 300]
    metrics = compute_token_metrics(calls)

    assert metrics.total_tokens == 600
    assert metrics.total_calls == 3
    assert abs(metrics.mean_tokens_per_alert - 200.0) < 1e-6
    assert metrics.p95_tokens_per_alert >= 250.0


def test_false_alarm_rate_hand_computed() -> None:
    """Hand-computed test for false alarm rate."""
    t0 = datetime(2026, 6, 1, 0, 0, 0, tzinfo=UTC)
    alerts = [AlertItem(f"A{i}", f"INV-{i:02d}", t0 + timedelta(hours=i)) for i in range(1, 11)]
    # 10 alerts across 20 devices over 2.0 days -> 10 / (20 * 2) = 0.25 per device-day
    far = compute_false_alarm_rate(alerts, device_count=20, duration_days=2.0)
    assert abs(far - 0.25) < 1e-6


def test_bootstrap_ci_reproducible_and_bounds() -> None:
    """Test bootstrap confidence interval computation."""
    data = [10.0, 10.0, 10.0, 10.0]
    low, high = bootstrap_ci(data, n_resamples=100, seed=123)
    assert abs(low - 10.0) < 1e-6
    assert abs(high - 10.0) < 1e-6

    # Normal variation
    data_var = [1.0, 2.0, 3.0, 4.0, 5.0]
    low_var, high_var = bootstrap_ci(data_var, n_resamples=500, seed=42)
    assert 1.0 < low_var < 3.0
    assert 3.0 < high_var < 5.0
