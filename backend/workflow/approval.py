"""Human-in-the-loop approval records and gate management.

Purpose: Manages immutable operator approval decisions for remediation proposals.
Inputs: Proposal IDs, approver identities, decisions (approve/reject), and optional rationale.
Outputs: Immutable, validated ApprovalRecord instances with 30-minute expiration enforcement.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field

from backend.agents.guard import scan_free_text
from backend.common.errors import IIRError

APPROVAL_EXPIRY_MINUTES: int = 30
MAX_REASON_LENGTH: int = 300


class ApprovalDecision(str, Enum):
    """Permitted operator approval decisions."""

    APPROVE = "approve"
    REJECT = "reject"


class ApprovalAlreadyDecidedError(IIRError):
    """Raised when an approval decision is attempted on an already decided proposal."""


class ApprovalRecord(BaseModel):
    """Immutable record of an operator decision on an action proposal (SEC-22, SEC-23)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    proposal_id: str
    approver_id: str
    decision: ApprovalDecision
    reason: str | None = Field(default=None, max_length=MAX_REASON_LENGTH)
    timestamp: datetime

    def is_expired(self, now: datetime | None = None) -> bool:
        """Check if approval has passed the 30-minute validity window."""
        ref_time = now if now is not None else datetime.now(UTC)
        ts = self.timestamp if self.timestamp.tzinfo else self.timestamp.replace(tzinfo=UTC)
        ref = ref_time if ref_time.tzinfo else ref_time.replace(tzinfo=UTC)
        return ref - ts > timedelta(minutes=APPROVAL_EXPIRY_MINUTES)


class ApprovalStore:
    """Thread-safe, append-only store for approval decisions."""

    def __init__(self) -> None:
        self._decisions: dict[str, ApprovalRecord] = {}

    def record_decision(
        self,
        proposal_id: str,
        approver_id: str,
        decision: ApprovalDecision | str,
        reason: str | None = None,
        timestamp: datetime | None = None,
    ) -> ApprovalRecord:
        """Record an operator decision. Each proposal can only be decided once (SEC-23)."""
        if proposal_id in self._decisions:
            raise ApprovalAlreadyDecidedError(
                f"Proposal '{proposal_id}' has already been decided and cannot be changed"
            )

        dec_enum = (
            decision
            if isinstance(decision, ApprovalDecision)
            else ApprovalDecision(decision.lower())
        )

        sanitized_reason: str | None = None
        if reason:
            scanned = scan_free_text(reason)
            sanitized_reason = scanned[:MAX_REASON_LENGTH]

        record_ts = timestamp or datetime.now(UTC)
        if not record_ts.tzinfo:
            record_ts = record_ts.replace(tzinfo=UTC)

        record = ApprovalRecord(
            proposal_id=proposal_id,
            approver_id=approver_id,
            decision=dec_enum,
            reason=sanitized_reason,
            timestamp=record_ts,
        )

        self._decisions[proposal_id] = record
        return record

    def get_decision(self, proposal_id: str) -> ApprovalRecord | None:
        """Retrieve stored approval record if it exists."""
        return self._decisions.get(proposal_id)

    def is_approved(self, proposal_id: str, now: datetime | None = None) -> bool:
        """Check if proposal has an unexpired approve decision."""
        record = self.get_decision(proposal_id)
        if record is None:
            return False
        if record.decision != ApprovalDecision.APPROVE:
            return False
        return not record.is_expired(now)
