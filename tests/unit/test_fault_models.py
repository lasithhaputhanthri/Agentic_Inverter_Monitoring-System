"""Unit tests for fault injection models.

Purpose: Validates schemas, constraints, immutability, and isolation of fault definitions.
Inputs: Valid and invalid parameter dictionaries for FaultSpec and GroundTruthRecord.
Outputs: Pytest assertions verifying schema integrity.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from backend.common.schemas import TelemetryMessage
from backend.faults.models import FaultSpec, FaultType, GroundTruthRecord
from pydantic import ValidationError


def test_fault_spec_valid() -> None:
    """Ensure FaultSpec validates and holds expected values."""
    start = datetime(2026, 6, 1, 12, 0, 0, tzinfo=UTC)
    spec = FaultSpec(
        fault_id="FLT-0001",
        fault_type=FaultType.OVERHEATING,
        device_id="INV-01",
        start_ts=start,
        duration_s=600.0,
        severity=0.8,
    )
    assert spec.fault_id == "FLT-0001"
    assert spec.fault_type == FaultType.OVERHEATING
    assert spec.device_id == "INV-01"
    assert spec.start_ts == start
    assert spec.duration_s == 600.0
    assert spec.severity == 0.8


def test_fault_spec_frozen_and_extra_forbidden() -> None:
    """Ensure FaultSpec is immutable and rejects unknown fields."""
    start = datetime(2026, 6, 1, 12, 0, 0, tzinfo=UTC)
    spec = FaultSpec(
        fault_id="FLT-0001",
        fault_type=FaultType.GRID_SAG,
        device_id="INV-02",
        start_ts=start,
        duration_s=300.0,
        severity=0.5,
    )
    with pytest.raises(ValidationError):
        spec.severity = 0.9

    with pytest.raises(ValidationError):
        FaultSpec(
            fault_id="FLT-0001",
            fault_type=FaultType.GRID_SAG,
            device_id="INV-02",
            start_ts=start,
            duration_s=300.0,
            severity=0.5,
            extra_field="rejected",  # type: ignore[call-arg]
        )


def test_fault_spec_constraints() -> None:
    """Verify field constraints: regex device_id/fault_id, duration_s > 0, severity in [0, 1]."""
    start = datetime(2026, 6, 1, 12, 0, 0, tzinfo=UTC)

    # Invalid fault_id pattern
    with pytest.raises(ValidationError):
        FaultSpec(
            fault_id="INVALID",
            fault_type=FaultType.OVERHEATING,
            device_id="INV-01",
            start_ts=start,
            duration_s=600.0,
            severity=0.5,
        )

    # Invalid device_id pattern
    with pytest.raises(ValidationError):
        FaultSpec(
            fault_id="FLT-0001",
            fault_type=FaultType.OVERHEATING,
            device_id="UNKNOWN-01",
            start_ts=start,
            duration_s=600.0,
            severity=0.5,
        )

    # duration_s <= 0
    with pytest.raises(ValidationError):
        FaultSpec(
            fault_id="FLT-0001",
            fault_type=FaultType.OVERHEATING,
            device_id="INV-01",
            start_ts=start,
            duration_s=0.0,
            severity=0.5,
        )

    # severity out of range
    with pytest.raises(ValidationError):
        FaultSpec(
            fault_id="FLT-0001",
            fault_type=FaultType.OVERHEATING,
            device_id="INV-01",
            start_ts=start,
            duration_s=600.0,
            severity=1.5,
        )


def test_ground_truth_record_from_fault() -> None:
    """Ensure GroundTruthRecord can be derived from a FaultSpec with accurate injected_at."""
    start = datetime(2026, 6, 1, 12, 0, 0, tzinfo=UTC)
    injected_at = start + timedelta(seconds=15)
    spec = FaultSpec(
        fault_id="FLT-0002",
        fault_type=FaultType.RELAY_STUCK,
        device_id="INV-05",
        start_ts=start,
        duration_s=900.0,
        severity=1.0,
    )

    record = GroundTruthRecord.from_fault(spec, injected_at)
    assert record.fault_id == spec.fault_id
    assert record.fault_type == spec.fault_type
    assert record.device_id == spec.device_id
    assert record.start_ts == spec.start_ts
    assert record.duration_s == spec.duration_s
    assert record.severity == spec.severity
    assert record.injected_at == injected_at


def test_monitor_input_model_isolation() -> None:
    """Acceptance test: The monitor's input model has no field named fault or ground_truth."""
    fields = set(TelemetryMessage.model_fields.keys())
    assert "fault" not in fields, "TelemetryMessage must not expose fault metadata"
    assert "ground_truth" not in fields, "TelemetryMessage must not expose ground_truth metadata"
    assert "fault_type" not in fields
