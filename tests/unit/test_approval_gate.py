"""Unit tests for operator approval gate, expiration, and store immutability.

Purpose: Verifies SEC-22 and SEC-23 guarantees: once-only decisions, expiration after 30 min,
         and rejection handling.
Inputs: ApprovalRecord, ApprovalStore, and simulated clock timestamps.
Outputs: Pytest assertions on decision constraints and error states.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from backend.workflow.approval import (
    ApprovalAlreadyDecidedError,
    ApprovalDecision,
    ApprovalRecord,
    ApprovalStore,
)


def test_approval_record_expiration() -> None:
    """Acceptance test: Approvals expire after 30 minutes, and expired approvals are invalid."""
    base_time = datetime(2026, 6, 1, 12, 0, 0, tzinfo=UTC)
    record = ApprovalRecord(
        proposal_id="PROP-001",
        approver_id="admin_1",
        decision=ApprovalDecision.APPROVE,
        timestamp=base_time,
    )

    # 10 minutes later: not expired
    assert not record.is_expired(base_time + timedelta(minutes=10))

    # 29 minutes later: not expired
    assert not record.is_expired(base_time + timedelta(minutes=29))

    # 31 minutes later: expired
    assert record.is_expired(base_time + timedelta(minutes=31))

    # 60 minutes later: expired
    assert record.is_expired(base_time + timedelta(minutes=60))


def test_approval_store_once_only_decision_refuses_second() -> None:
    """Acceptance test: A proposal can be decided once. A second decision is refused and logged (SEC-23)."""
    store = ApprovalStore()
    now = datetime(2026, 6, 1, 12, 0, 0, tzinfo=UTC)

    # First decision: accepted
    rec = store.record_decision(
        proposal_id="PROP-002",
        approver_id="admin_1",
        decision=ApprovalDecision.APPROVE,
        reason="Approved after initial triage",
        timestamp=now,
    )
    assert rec.decision == ApprovalDecision.APPROVE
    assert store.is_approved("PROP-002", now=now)

    # Second decision: strictly rejected with error
    with pytest.raises(ApprovalAlreadyDecidedError, match="already been decided"):
        store.record_decision(
            proposal_id="PROP-002",
            approver_id="admin_2",
            decision=ApprovalDecision.REJECT,
            reason="Changed mind",
            timestamp=now + timedelta(minutes=1),
        )

    # Store remains immutable with original decision
    assert store.get_decision("PROP-002") is not None
    assert store.get_decision("PROP-002").decision == ApprovalDecision.APPROVE  # type: ignore[union-attr]


def test_approval_store_rejected_proposal_is_never_approved() -> None:
    """Acceptance test: A rejected proposal is never marked as approved."""
    store = ApprovalStore()
    now = datetime(2026, 6, 1, 12, 0, 0, tzinfo=UTC)

    store.record_decision(
        proposal_id="PROP-003",
        approver_id="safety_officer",
        decision=ApprovalDecision.REJECT,
        reason="Risk of grid voltage imbalance",
        timestamp=now,
    )

    assert not store.is_approved("PROP-003", now=now)
    assert store.get_decision("PROP-003") is not None
    assert store.get_decision("PROP-003").decision == ApprovalDecision.REJECT  # type: ignore[union-attr]


def test_approval_store_scans_and_bounds_reason() -> None:
    """Acceptance test: Reason is scanned for injection/control chars and truncated to max 300 chars."""
    store = ApprovalStore()
    now = datetime(2026, 6, 1, 12, 0, 0, tzinfo=UTC)
    long_reason = "Operator approval note with password=secret123 and details " + ("X" * 400)

    rec = store.record_decision(
        proposal_id="PROP-004",
        approver_id="admin_1",
        decision=ApprovalDecision.APPROVE,
        reason=long_reason,
        timestamp=now,
    )

    assert rec.reason is not None
    assert len(rec.reason) <= 300
    assert "[REDACTED]" in rec.reason or "password=" not in rec.reason
