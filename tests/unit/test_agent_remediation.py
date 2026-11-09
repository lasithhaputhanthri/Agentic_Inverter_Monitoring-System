"""Unit tests for the RemediationAgent.

Purpose: Verifies action proposal generation, SEC-33 device verification, retries,
         fallbacks, and output text guard scanning.
Inputs: Alert and DiagnosisResult instances, scripted responses.
Outputs: Pytest assertions verifying remediation safety.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest
from backend.agents.llm_client import FakeLLMClient
from backend.agents.models import (
    DiagnosisCause,
    DiagnosisResult,
    RemediationAction,
)
from backend.agents.remediation import RemediationAgent
from backend.monitor.models import Alert, AlertSeverity, MonitorRule


def _make_context(dev_id: str = "INV-01") -> tuple[Alert, DiagnosisResult]:
    alert = Alert.create(
        device_id=dev_id,
        ts=datetime(2026, 6, 1, 12, 0, 0, tzinfo=UTC),
        rule=MonitorRule.TEMP_HIGH_FOR_POWER,
        severity=AlertSeverity.WARNING,
        observed=65.0,
        threshold=12.0,
    )
    diag = DiagnosisResult(
        device_id=dev_id,
        cause=DiagnosisCause.OVERHEATING,
        confidence=0.9,
        evidence=["Overheating observed"],
        prompt_version="diagnosis_v1",
        model="mock-model",
    )
    return alert, diag


def test_remediation_agent_valid_proposal() -> None:
    """Ensure valid remediation proposal succeeds and adheres to schema."""
    scripted = json.dumps(
        {
            "action": "reduce_load",
            "justification": "Throttle setpoint to 80% to alleviate thermal rise.",
        }
    )
    client = FakeLLMClient(scripted_responses=[scripted])
    agent = RemediationAgent(client=client)

    alert, diag = _make_context("INV-01")
    proposal = agent.propose_action(alert, diag)

    assert proposal.device_id == "INV-01"
    assert proposal.action == RemediationAction.REDUCE_LOAD
    assert "Throttle setpoint" in proposal.justification
    assert client.call_count == 1


def test_remediation_agent_sec33_device_mismatch_rejected() -> None:
    """Acceptance test: SEC-33: A proposal can name only the device in its alert. Mismatch fails."""
    # 1. Diagnosis device differs from alert device
    alert, diag = _make_context("INV-01")
    mismatched_diag = DiagnosisResult(
        device_id="INV-02",  # Different device!
        cause=DiagnosisCause.OVERHEATING,
        confidence=0.9,
        evidence=["Overheating"],
        prompt_version="diagnosis_v1",
        model="mock-model",
    )
    client = FakeLLMClient()
    agent = RemediationAgent(client=client)

    with pytest.raises(ValueError, match="Device mismatch"):
        agent.propose_action(alert, mismatched_diag)

    # 2. Model outputs a different device_id
    scripted_spoof = json.dumps(
        {
            "device_id": "INV-99",  # Attacker spoofing different device
            "action": "reset_relay",
            "justification": "Reset spoofed device",
        }
    )
    client2 = FakeLLMClient(scripted_responses=[scripted_spoof, scripted_spoof])
    agent2 = RemediationAgent(client=client2)

    # Mismatch triggers validation failure -> retry -> fallback to no_action on alert device
    fallback_prop = agent2.propose_action(alert, diag)
    assert fallback_prop.device_id == "INV-01"
    assert fallback_prop.action == RemediationAction.NO_ACTION


def test_remediation_agent_fallback_to_no_action() -> None:
    """Acceptance test: Two failures produce no_action with schema_failure recorded."""
    client = FakeLLMClient(scripted_responses=["INVALID", "INVALID"])
    agent = RemediationAgent(client=client)

    alert, diag = _make_context("INV-01")
    proposal = agent.propose_action(alert, diag)

    assert proposal.action == RemediationAction.NO_ACTION
    assert agent.last_call_metadata["status"] == "schema_failure"


def test_remediation_agent_output_guard_sanitizes_justification() -> None:
    """Ensure output scanner redacts leaked credentials or system paths from justification."""
    scripted_leak = json.dumps(
        {
            "action": "schedule_inspection",
            "justification": "Inspection needed. Key: api_key=supersecret123 at /etc/shadow",
        }
    )
    client = FakeLLMClient(scripted_responses=[scripted_leak])
    agent = RemediationAgent(client=client)

    alert, diag = _make_context("INV-01")
    proposal = agent.propose_action(alert, diag)

    assert "supersecret123" not in proposal.justification
    assert "[REDACTED:SECRET]" in proposal.justification
    assert "/etc/shadow" not in proposal.justification
    assert "[REDACTED:PATH]" in proposal.justification
