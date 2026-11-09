"""Isolated remediation executor with strict safety gates.

Purpose: Executes approved remediation proposals against the simulator state API only.
Inputs: ActionProposal, DiagnosisResult, Alert, ApprovalStore, and PolicyEngine.
Outputs: Validated, idempotent ExecutionResult without external system, file, or network access.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

from backend.agents.models import ActionProposal, DiagnosisResult, RemediationAction
from backend.executor.actions import (
    SimulatorStateAPI,
    execute_no_action,
    execute_reduce_load,
    execute_reset_relay,
    execute_schedule_inspection,
)
from backend.executor.policy import PolicyEngine
from backend.monitor.models import Alert
from backend.workflow.approval import ApprovalDecision, ApprovalRecord, ApprovalStore
from backend.workflow.audit import AuditEventType, AuditSink

RATE_LIMIT_WINDOW = timedelta(hours=1)


@dataclass(frozen=True)
class ExecutionResult:
    """Immutable result of an execution attempt (SEC-42)."""

    execution_key: str
    device_id: str
    action: RemediationAction
    executed: bool
    status: str
    reason: str | None = None
    details: dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))


class IsolatedExecutor:
    """Execution engine strictly isolated from host OS, files, and network (SEC-41)."""

    def __init__(
        self,
        simulator_api: SimulatorStateAPI,
        policy_engine: PolicyEngine,
        approval_store: ApprovalStore,
        audit_sink: AuditSink | None = None,
    ) -> None:
        self.api = simulator_api
        self.policy = policy_engine
        self.approvals = approval_store
        self.audit = audit_sink

        # Idempotency cache: execution_key -> ExecutionResult (SEC-42)
        self._execution_history: dict[str, ExecutionResult] = {}
        # Device rate limit: device_id -> last_execution_time (1 per device per hour)
        self._device_last_executed: dict[str, datetime] = {}

    def execute(
        self,
        proposal: ActionProposal,
        diagnosis: DiagnosisResult,
        alert: Alert,
        current_time: datetime | None = None,
    ) -> ExecutionResult:
        """Execute an approved action after passing all mandatory verification gates."""
        now = current_time or datetime.now(UTC)
        if not now.tzinfo:
            now = now.replace(tzinfo=UTC)

        exec_key = str(proposal.proposal_id)

        # 1. Idempotency Check: repeated execution key returns stored result (SEC-42)
        if exec_key in self._execution_history:
            return self._execution_history[exec_key]

        # 2. Device Mismatch Gate: proposal device must match alert device (SEC-33)
        if proposal.device_id != alert.device_id:
            return self._refuse(
                exec_key=exec_key,
                device_id=proposal.device_id,
                action=proposal.action,
                reason="device_mismatch",
                details={"alert_device": alert.device_id, "proposal_device": proposal.device_id},
                now=now,
            )

        # 3. Simulator Registry Gate: device must exist in simulator (SEC-40)
        if not self.api.has_device(proposal.device_id):
            return self._refuse(
                exec_key=exec_key,
                device_id=proposal.device_id,
                action=proposal.action,
                reason="unknown_device",
                details={"device_id": proposal.device_id},
                now=now,
            )

        # 4. Approval Gate: must exist, be approved, and not expired (SEC-22, SEC-23)
        approval_record: ApprovalRecord | None = self.approvals.get_decision(exec_key)
        if approval_record is None:
            return self._refuse(
                exec_key=exec_key,
                device_id=proposal.device_id,
                action=proposal.action,
                reason="unapproved_proposal",
                details={"proposal_id": exec_key},
                now=now,
            )

        if approval_record.decision != ApprovalDecision.APPROVE:
            return self._refuse(
                exec_key=exec_key,
                device_id=proposal.device_id,
                action=proposal.action,
                reason="approval_rejected",
                details={"decision": approval_record.decision.value},
                now=now,
            )

        if approval_record.is_expired(now):
            if self.audit:
                self.audit.record(
                    AuditEventType.EXPIRED,
                    {"proposal_id": exec_key, "device_id": proposal.device_id},
                    timestamp=now,
                )
            return self._refuse(
                exec_key=exec_key,
                device_id=proposal.device_id,
                action=proposal.action,
                reason="approval_expired",
                details={"approval_time": approval_record.timestamp.isoformat()},
                now=now,
            )

        # 5. Policy Table Gate: (cause, action) must be permitted (SEC-43)
        if not self.policy.is_allowed(diagnosis.cause, proposal.action):
            if self.audit:
                self.audit.record(
                    AuditEventType.POLICY_BLOCKED,
                    {
                        "proposal_id": exec_key,
                        "device_id": proposal.device_id,
                        "cause": diagnosis.cause.value,
                        "action": proposal.action.value,
                    },
                    timestamp=now,
                )
            return self._refuse(
                exec_key=exec_key,
                device_id=proposal.device_id,
                action=proposal.action,
                reason="policy_blocked",
                details={"cause": diagnosis.cause.value, "action": proposal.action.value},
                now=now,
            )

        # 6. Rate Limit Gate: max 1 action per device per hour
        last_exec = self._device_last_executed.get(proposal.device_id)
        if last_exec is not None and (now - last_exec) < RATE_LIMIT_WINDOW:
            return self._refuse(
                exec_key=exec_key,
                device_id=proposal.device_id,
                action=proposal.action,
                reason="rate_limit_exceeded",
                details={"last_execution": last_exec.isoformat()},
                now=now,
            )

        # All gates passed: apply action through the public simulator state method
        details: dict[str, Any]
        if proposal.action == RemediationAction.REDUCE_LOAD:
            details = execute_reduce_load(self.api, proposal.device_id)
        elif proposal.action == RemediationAction.RESET_RELAY:
            details = execute_reset_relay(self.api, proposal.device_id)
        elif proposal.action == RemediationAction.SCHEDULE_INSPECTION:
            details = execute_schedule_inspection(
                self.api, proposal.device_id, f"Inspection: {proposal.justification[:100]}"
            )
        elif proposal.action == RemediationAction.NO_ACTION:
            details = execute_no_action(self.api, proposal.device_id)
        else:
            return self._refuse(
                exec_key=exec_key,
                device_id=proposal.device_id,
                action=proposal.action,
                reason="invalid_action_type",
                details={},
                now=now,
            )

        res = ExecutionResult(
            execution_key=exec_key,
            device_id=proposal.device_id,
            action=proposal.action,
            executed=True,
            status="executed",
            details=details,
            timestamp=now,
        )

        self._execution_history[exec_key] = res
        self._device_last_executed[proposal.device_id] = now

        if self.audit:
            self.audit.record(
                AuditEventType.EXECUTED,
                {
                    "proposal_id": exec_key,
                    "device_id": proposal.device_id,
                    "action": proposal.action.value,
                },
                timestamp=now,
            )

        return res

    def _refuse(
        self,
        exec_key: str,
        device_id: str,
        action: RemediationAction,
        reason: str,
        details: dict[str, Any],
        now: datetime,
    ) -> ExecutionResult:
        """Record and audit execution refusal."""
        res = ExecutionResult(
            execution_key=exec_key,
            device_id=device_id,
            action=action,
            executed=False,
            status="refused",
            reason=reason,
            details=details,
            timestamp=now,
        )
        self._execution_history[exec_key] = res

        if self.audit:
            self.audit.record(
                AuditEventType.EXECUTION_REFUSED,
                {
                    "proposal_id": exec_key,
                    "device_id": device_id,
                    "action": action.value,
                    "reason": reason,
                },
                timestamp=now,
            )

        return res
