"""Acceptance test for Phase 5 demo run and audit deliverable.

Purpose: Verifies acceptance test: Run one alert from detection to approval prompt
         to execution, print audit log, and save to docs/demo/phase5_audit.txt with no site data.
Inputs: Demo alert scenario and FakeLLMClient.
Outputs: docs/demo/phase5_audit.txt and pytest assertions on audit event sequence.
"""

from __future__ import annotations

from pathlib import Path

from backend.workflow.audit import AuditEventType
from backend.workflow.demo import DEMO_OUTPUT_FILE, run_phase5_demo


def test_phase5_demo_execution_and_audit_deliverable(tmp_path: Path) -> None:
    """Acceptance test: Complete demo runs, generates deliverable, and validates audit events."""
    events = run_phase5_demo(DEMO_OUTPUT_FILE)

    assert DEMO_OUTPUT_FILE.exists(), "docs/demo/phase5_audit.txt deliverable must exist"
    content = DEMO_OUTPUT_FILE.read_text(encoding="utf-8")

    # Verify key audit trail sequence
    event_types = [e.event_type for e in events]
    assert AuditEventType.ALERT_RAISED in event_types
    assert AuditEventType.DIAGNOSIS_MADE in event_types
    assert AuditEventType.PROPOSAL_MADE in event_types
    assert AuditEventType.APPROVAL_REQUESTED in event_types
    assert AuditEventType.APPROVED in event_types
    assert AuditEventType.EXECUTED in event_types

    # Verify no site-specific sensitive data appears in audit log
    assert "password" not in content.lower()
    assert "api_key" not in content.lower()
    assert "secret" not in content.lower()
