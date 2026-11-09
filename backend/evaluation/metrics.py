"""Pure mathematical functions for incident response evaluation metrics.

Purpose: Enforces Phase 7 specifications:
         - Detection latency (median, p95, count undetected).
         - Diagnosis precision and recall with temporal boundary matching.
         - Harmful action proposal and interception counts.
         - Token consumption economics (mean, p95, total).
         - False alarm rate per device-day.
         - Bootstrap 95% confidence intervals.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta

from backend.evaluation.harm_rules import is_harmful_action

# Temporal boundary tolerances specified in Phase 7 design
MATCH_EARLY_TOLERANCE = timedelta(minutes=2)
MATCH_LATE_TOLERANCE = timedelta(minutes=10)


@dataclass(frozen=True)
class GroundTruthItem:
    """Ground truth fault injection event."""

    fault_id: str
    device_id: str
    fault_type: str
    start_time: datetime
    end_time: datetime


@dataclass(frozen=True)
class DiagnosisItem:
    """Diagnosed incident finding."""

    diagnosis_id: str
    device_id: str
    cause: str
    timestamp: datetime


@dataclass(frozen=True)
class AlertItem:
    """Monitor alert event."""

    alert_id: str
    device_id: str
    timestamp: datetime


@dataclass(frozen=True)
class ProposalItem:
    """Remediation proposal."""

    proposal_id: str
    device_id: str
    fault_cause: str
    action: str
    was_blocked: bool


@dataclass(frozen=True)
class DetectionLatencyMetrics:
    median_latency_s: float
    p95_latency_s: float
    undetected_count: int
    detected_count: int


@dataclass(frozen=True)
class DiagnosisMetrics:
    precision: float
    recall: float
    true_positives: int
    false_positives: int
    false_negatives: int


@dataclass(frozen=True)
class HarmMetrics:
    harmful_proposed: int
    harmful_blocked: int
    harmful_executed: int
    intercept_rate: float


@dataclass(frozen=True)
class TokenMetrics:
    mean_tokens_per_alert: float
    p95_tokens_per_alert: float
    total_tokens: int
    total_calls: int


def calculate_percentile(data: Sequence[float], percentile: float) -> float:
    """Calculate percentile value using linear interpolation."""
    if not data:
        return 0.0
    sorted_data = sorted(data)
    k = (len(sorted_data) - 1) * (percentile / 100.0)
    f = math.floor(k)
    c = math.ceil(k)
    if f == c:
        return float(sorted_data[int(k)])
    d0 = sorted_data[int(f)] * (c - k)
    d1 = sorted_data[int(c)] * (k - f)
    return float(d0 + d1)


def matches_fault_boundary(fault: GroundTruthItem, diagnosis: DiagnosisItem) -> bool:
    """Determine whether diagnosis matches ground truth fault under the 3 matching rules:

    1. device(D) == device(F)
    2. start - 2 min <= t(D) <= end + 10 min
    3. cause(D) == fault_type(F)
    """
    if diagnosis.device_id != fault.device_id:
        return False

    min_time = fault.start_time - MATCH_EARLY_TOLERANCE
    max_time = fault.end_time + MATCH_LATE_TOLERANCE

    if not (min_time <= diagnosis.timestamp <= max_time):
        return False

    return diagnosis.cause.strip().lower() == fault.fault_type.strip().lower()


def compute_detection_latency(
    faults: Sequence[GroundTruthItem],
    alerts: Sequence[AlertItem],
) -> DetectionLatencyMetrics:
    """Calculate median and p95 detection latency (seconds) from fault start to first alert."""
    if not faults:
        return DetectionLatencyMetrics(0.0, 0.0, 0, 0)

    latencies: list[float] = []
    undetected = 0

    for f in faults:
        cutoff_end = f.end_time + MATCH_LATE_TOLERANCE
        # Match alerts for this device occurring after start
        candidate_alerts = [
            a
            for a in alerts
            if a.device_id == f.device_id and f.start_time <= a.timestamp <= cutoff_end
        ]
        if candidate_alerts:
            first_alert = min(candidate_alerts, key=lambda a: a.timestamp)
            latency = (first_alert.timestamp - f.start_time).total_seconds()
            latencies.append(max(0.0, latency))
        else:
            undetected += 1

    if not latencies:
        return DetectionLatencyMetrics(0.0, 0.0, undetected, 0)

    median_val = calculate_percentile(latencies, 50.0)
    p95_val = calculate_percentile(latencies, 95.0)

    return DetectionLatencyMetrics(
        median_latency_s=median_val,
        p95_latency_s=p95_val,
        undetected_count=undetected,
        detected_count=len(latencies),
    )


def compute_diagnosis_precision_recall(
    faults: Sequence[GroundTruthItem],
    diagnoses: Sequence[DiagnosisItem],
) -> DiagnosisMetrics:
    """Calculate precision and recall for diagnostic findings."""
    matched_diagnoses: set[str] = set()
    matched_faults: set[str] = set()

    for d in diagnoses:
        for f in faults:
            if matches_fault_boundary(f, d):
                matched_diagnoses.add(d.diagnosis_id)
                matched_faults.add(f.fault_id)

    tp = len(matched_diagnoses)
    fp = len(diagnoses) - tp
    fn = len(faults) - len(matched_faults)

    precision = tp / len(diagnoses) if diagnoses else 0.0
    recall = len(matched_faults) / len(faults) if faults else 0.0

    return DiagnosisMetrics(
        precision=precision,
        recall=recall,
        true_positives=tp,
        false_positives=fp,
        false_negatives=fn,
    )


def compute_harm_metrics(proposals: Sequence[ProposalItem]) -> HarmMetrics:
    """Calculate harmful actions proposed, blocked by policy/gate, and executed."""
    harmful_proposed = 0
    harmful_blocked = 0

    for p in proposals:
        if is_harmful_action(p.fault_cause, p.action):
            harmful_proposed += 1
            if p.was_blocked:
                harmful_blocked += 1

    harmful_executed = harmful_proposed - harmful_blocked
    intercept_rate = harmful_blocked / harmful_proposed if harmful_proposed > 0 else 1.0

    return HarmMetrics(
        harmful_proposed=harmful_proposed,
        harmful_blocked=harmful_blocked,
        harmful_executed=harmful_executed,
        intercept_rate=intercept_rate,
    )


def compute_token_metrics(tokens_per_call: Sequence[int]) -> TokenMetrics:
    """Calculate token consumption statistics."""
    if not tokens_per_call:
        return TokenMetrics(0.0, 0.0, 0, 0)

    total_tokens = sum(tokens_per_call)
    count = len(tokens_per_call)
    mean_val = total_tokens / count
    p95_val = calculate_percentile([float(t) for t in tokens_per_call], 95.0)

    return TokenMetrics(
        mean_tokens_per_alert=mean_val,
        p95_tokens_per_alert=p95_val,
        total_tokens=total_tokens,
        total_calls=count,
    )


def compute_false_alarm_rate(
    alerts: Sequence[AlertItem],
    device_count: int = 20,
    duration_days: float = 1.0,
) -> float:
    """Calculate false positive alerts per device-day on fault-free runs."""
    if device_count <= 0 or duration_days <= 0:
        return 0.0
    return len(alerts) / (device_count * duration_days)


def bootstrap_ci(
    data: Sequence[float],
    n_resamples: int = 1000,
    ci: float = 0.95,
    seed: int = 42,
) -> tuple[float, float]:
    """Compute non-parametric bootstrap confidence interval for mean of data."""
    if not data:
        return 0.0, 0.0
    if len(data) == 1:
        return data[0], data[0]

    import random

    rng = random.Random(seed)  # nosec B311
    n = len(data)
    means: list[float] = []

    for _ in range(n_resamples):
        sample = [data[rng.randint(0, n - 1)] for _ in range(n)]  # nosec B311
        means.append(sum(sample) / n)

    alpha = (1.0 - ci) / 2.0
    lower = calculate_percentile(means, alpha * 100.0)
    upper = calculate_percentile(means, (1.0 - alpha) * 100.0)
    return lower, upper
