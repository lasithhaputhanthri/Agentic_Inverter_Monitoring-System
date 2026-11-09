"""Unit tests for agent output models and schema validation.

Purpose: Validates constraints, immutability, extra-field prohibition, and validation bounds
         for DiagnosisResult and ActionProposal.
Inputs: Valid and invalid test payloads.
Outputs: Pytest assertions verifying schema enforcement.
"""

from __future__ import annotations

import pytest
from backend.agents.models import (
    ActionProposal,
    DiagnosisCause,
    DiagnosisResult,
    RemediationAction,
)
from pydantic import ValidationError


def test_diagnosis_result_valid() -> None:
    """Ensure DiagnosisResult validates properly with conforming fields."""
    diag = DiagnosisResult(
        device_id="INV-01",
        cause=DiagnosisCause.OVERHEATING,
        confidence=0.95,
        evidence=["Temperature exceeds expected by 25C", "Ambient is 25C"],
        prompt_version="diagnosis_v1",
        model="test-model",
    )
    assert diag.device_id == "INV-01"
    assert diag.cause == DiagnosisCause.OVERHEATING
    assert diag.confidence == 0.95
    assert len(diag.evidence) == 2


def test_diagnosis_result_rejects_extra_fields() -> None:
    """Acceptance test: Extra fields are rejected (extra='forbid')."""
    with pytest.raises(ValidationError):
        DiagnosisResult(
            device_id="INV-01",
            cause=DiagnosisCause.OVERHEATING,
            confidence=0.9,
            evidence=["Valid evidence"],
            prompt_version="diagnosis_v1",
            model="test-model",
            extra_field="unauthorized",  # type: ignore[call-arg]
        )


def test_diagnosis_result_rejects_invalid_enums_and_confidence() -> None:
    """Acceptance test: Wrong enum values and out-of-range confidence fail validation."""
    # Invalid cause enum
    with pytest.raises(ValidationError):
        DiagnosisResult(
            device_id="INV-01",
            cause="non_existent_cause",  # type: ignore[arg-type]
            confidence=0.8,
            evidence=["Valid evidence"],
            prompt_version="diagnosis_v1",
            model="test-model",
        )

    # Confidence > 1.0
    with pytest.raises(ValidationError):
        DiagnosisResult(
            device_id="INV-01",
            cause=DiagnosisCause.GRID_SAG,
            confidence=1.5,
            evidence=["Valid evidence"],
            prompt_version="diagnosis_v1",
            model="test-model",
        )

    # Confidence < 0.0
    with pytest.raises(ValidationError):
        DiagnosisResult(
            device_id="INV-01",
            cause=DiagnosisCause.GRID_SAG,
            confidence=-0.1,
            evidence=["Valid evidence"],
            prompt_version="diagnosis_v1",
            model="test-model",
        )


def test_diagnosis_result_evidence_bounds() -> None:
    """Ensure evidence list has between 1 and 3 items and each <= 200 characters."""
    # Empty evidence
    with pytest.raises(ValidationError):
        DiagnosisResult(
            device_id="INV-01",
            cause=DiagnosisCause.UNKNOWN,
            confidence=0.0,
            evidence=[],
            prompt_version="diagnosis_v1",
            model="test-model",
        )

    # > 3 items
    with pytest.raises(ValidationError):
        DiagnosisResult(
            device_id="INV-01",
            cause=DiagnosisCause.UNKNOWN,
            confidence=0.0,
            evidence=["1", "2", "3", "4"],
            prompt_version="diagnosis_v1",
            model="test-model",
        )

    # Item > 200 chars
    with pytest.raises(ValidationError):
        DiagnosisResult(
            device_id="INV-01",
            cause=DiagnosisCause.UNKNOWN,
            confidence=0.0,
            evidence=["A" * 201],
            prompt_version="diagnosis_v1",
            model="test-model",
        )


def test_action_proposal_valid() -> None:
    """Ensure ActionProposal validates properly with conforming fields."""
    prop = ActionProposal(
        device_id="INV-02",
        action=RemediationAction.REDUCE_LOAD,
        justification="Thermal stress mitigation for confirmed inverter overheating.",
        diagnosis_ref="overheating",
        prompt_version="remediation_v1",
        model="test-model",
    )
    assert prop.device_id == "INV-02"
    assert prop.action == RemediationAction.REDUCE_LOAD
    assert prop.justification.startswith("Thermal stress")


def test_action_proposal_rejects_extra_fields_and_long_justification() -> None:
    """Acceptance test: Extra fields and justification > 300 characters are rejected."""
    # Extra field
    with pytest.raises(ValidationError):
        ActionProposal(
            device_id="INV-02",
            action=RemediationAction.NO_ACTION,
            justification="Safe state",
            diagnosis_ref="unknown",
            prompt_version="remediation_v1",
            model="test-model",
            unauthorized="injection",  # type: ignore[call-arg]
        )

    # Justification > 300 characters
    with pytest.raises(ValidationError):
        ActionProposal(
            device_id="INV-02",
            action=RemediationAction.NO_ACTION,
            justification="A" * 301,
            diagnosis_ref="unknown",
            prompt_version="remediation_v1",
            model="test-model",
        )
