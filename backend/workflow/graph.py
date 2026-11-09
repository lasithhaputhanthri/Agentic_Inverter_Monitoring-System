"""LangGraph multi-agent incident response workflow.

Purpose: Orchestrates incident flow from monitor alert through diagnosis, proposal, policy gate,
         mandatory human approval interrupt, isolated execution, and final record.
Inputs: Alert, telemetry stores, agent instances, policy engine, and approval gate.
Outputs: Compiled LangGraph state machine with SQLite checkpointer state persistence.
"""

from __future__ import annotations

import sqlite3
from dataclasses import asdict
from datetime import datetime
from typing import Any, TypedDict

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from backend.agents.diagnosis import DiagnosisAgent
from backend.agents.models import ActionProposal, DiagnosisResult
from backend.agents.remediation import RemediationAgent
from backend.executor.executor import ExecutionResult, IsolatedExecutor
from backend.executor.policy import PolicyEngine
from backend.monitor.models import Alert
from backend.workflow.approval import (
    ApprovalAlreadyDecidedError,
    ApprovalDecision,
    ApprovalRecord,
    ApprovalStore,
)
from backend.workflow.audit import AuditEventType, AuditSink


class IncidentState(TypedDict, total=False):
    """Workflow state schema for an inverter incident."""

    incident_id: str
    alert: Alert
    telemetry: list[dict[str, Any]] | None
    snapshot: dict[str, dict[str, Any]] | None
    limits_ok: bool
    diagnosis: DiagnosisResult | None
    proposal: ActionProposal | None
    policy_allowed: bool
    approval: ApprovalRecord | None
    execution_result: dict[str, Any] | None
    current_time: datetime | None
    status: str


def create_sqlite_checkpointer(db_path: str = ":memory:") -> SqliteSaver:
    """Create a SQLite-backed checkpointer for persistent workflow state."""
    conn = sqlite3.connect(db_path, check_same_thread=False)
    return SqliteSaver(conn)


def build_incident_workflow(
    diagnosis_agent: DiagnosisAgent,
    remediation_agent: RemediationAgent,
    policy_engine: PolicyEngine,
    executor: IsolatedExecutor,
    approval_store: ApprovalStore,
    audit_sink: AuditSink | None = None,
    checkpointer: BaseCheckpointSaver | None = None,
    interrupt_for_approval: bool = True,
) -> CompiledStateGraph:
    """Construct and compile the incident response StateGraph.

    Node order:
        ingest_alert -> check_limits -> diagnose -> propose -> policy_check
        -> await_approval (interrupt) -> execute_or_reject -> record
    """
    builder = StateGraph(IncidentState)

    # 1. Ingest Alert
    def ingest_alert_node(state: IncidentState) -> dict[str, Any]:
        alert = state["alert"]
        if isinstance(alert, dict):
            alert = Alert.model_validate(alert)
        incident_id = alert.alert_id

        if audit_sink:
            audit_sink.record(
                AuditEventType.ALERT_RAISED,
                {
                    "alert_id": alert.alert_id,
                    "device_id": alert.device_id,
                    "rule": alert.rule.value,
                    "severity": alert.severity.value,
                },
                timestamp=alert.ts,
            )

        return {
            "incident_id": incident_id,
            "alert": alert,
            "status": "ingested",
        }

    # 2. Check Limits
    def check_limits_node(state: IncidentState) -> dict[str, Any]:
        # Agent internal quota tracker will raise or enforce daily limit
        return {
            "limits_ok": True,
            "status": "limits_checked",
        }

    # 3. Diagnose
    def diagnose_node(state: IncidentState) -> dict[str, Any]:
        alert = state["alert"]
        telemetry = state.get("telemetry")
        snapshot = state.get("snapshot")

        diagnosis = diagnosis_agent.diagnose(alert, telemetry=telemetry, fleet_snapshot=snapshot)

        if audit_sink:
            audit_sink.record(
                AuditEventType.DIAGNOSIS_MADE,
                {
                    "alert_id": alert.alert_id,
                    "device_id": alert.device_id,
                    "cause": diagnosis.cause.value,
                    "confidence": diagnosis.confidence,
                },
            )

        return {
            "diagnosis": diagnosis,
            "status": "diagnosed",
        }

    # 4. Propose
    def propose_node(state: IncidentState) -> dict[str, Any]:
        alert = state["alert"]
        diagnosis = state["diagnosis"]
        assert diagnosis is not None

        proposal = remediation_agent.propose(alert, diagnosis)

        if audit_sink:
            audit_sink.record(
                AuditEventType.PROPOSAL_MADE,
                {
                    "proposal_id": proposal.proposal_id,
                    "device_id": proposal.device_id,
                    "action": proposal.action.value,
                },
            )

        return {
            "proposal": proposal,
            "status": "proposed",
        }

    # 5. Policy Check
    def policy_check_node(state: IncidentState) -> dict[str, Any]:
        diagnosis = state["diagnosis"]
        proposal = state["proposal"]
        assert diagnosis is not None and proposal is not None

        allowed = policy_engine.is_allowed(diagnosis.cause, proposal.action)

        if allowed:
            if audit_sink:
                audit_sink.record(
                    AuditEventType.APPROVAL_REQUESTED,
                    {
                        "proposal_id": proposal.proposal_id,
                        "device_id": proposal.device_id,
                        "action": proposal.action.value,
                    },
                )
            return {
                "policy_allowed": True,
                "status": "awaiting_approval",
            }
        else:
            if audit_sink:
                audit_sink.record(
                    AuditEventType.POLICY_BLOCKED,
                    {
                        "proposal_id": proposal.proposal_id,
                        "device_id": proposal.device_id,
                        "cause": diagnosis.cause.value,
                        "action": proposal.action.value,
                    },
                )
            return {
                "policy_allowed": False,
                "status": "policy_blocked",
            }

    # 6. Await Approval (Interrupted before this node or resumes here)
    def await_approval_node(state: IncidentState) -> dict[str, Any]:
        proposal = state.get("proposal")
        approval = state.get("approval")

        if proposal is not None and approval is not None:
            # Sync to approval store if not already present
            try:
                approval_store.record_decision(
                    proposal_id=approval.proposal_id,
                    approver_id=approval.approver_id,
                    decision=approval.decision,
                    reason=approval.reason,
                    timestamp=approval.timestamp,
                )
            except ApprovalAlreadyDecidedError:
                pass

            if audit_sink:
                ev_type = (
                    AuditEventType.APPROVED
                    if approval.decision == ApprovalDecision.APPROVE
                    else AuditEventType.REJECTED
                )
                audit_sink.record(
                    ev_type,
                    {
                        "proposal_id": approval.proposal_id,
                        "approver_id": approval.approver_id,
                        "decision": approval.decision.value,
                    },
                    timestamp=approval.timestamp,
                )

        return {"status": "approval_resolved"}

    # 7. Execute or Reject
    def execute_or_reject_node(state: IncidentState) -> dict[str, Any]:
        alert = state["alert"]
        diagnosis = state.get("diagnosis")
        proposal = state.get("proposal")
        policy_allowed = state.get("policy_allowed", False)
        approval = state.get("approval")

        if not policy_allowed or diagnosis is None or proposal is None:
            res_dict = {
                "execution_key": proposal.proposal_id if proposal else "N/A",
                "device_id": alert.device_id,
                "executed": False,
                "status": "refused",
                "reason": "policy_blocked",
            }
            return {"execution_result": res_dict, "status": "executed_or_rejected"}

        if approval is None or approval.decision != ApprovalDecision.APPROVE:
            res_dict = {
                "execution_key": proposal.proposal_id,
                "device_id": alert.device_id,
                "executed": False,
                "status": "refused",
                "reason": "unapproved_or_rejected",
            }
            return {"execution_result": res_dict, "status": "executed_or_rejected"}

        # Run through isolated executor
        ref_time = state.get("current_time") or (approval.timestamp if approval else None)
        exec_res: ExecutionResult = executor.execute(
            proposal, diagnosis, alert, current_time=ref_time
        )
        return {
            "execution_result": asdict(exec_res),
            "status": "executed_or_rejected",
        }

    # 8. Record
    def record_node(state: IncidentState) -> dict[str, Any]:
        return {"status": "completed"}

    # Add nodes strictly in order
    builder.add_node("ingest_alert", ingest_alert_node)
    builder.add_node("check_limits", check_limits_node)
    builder.add_node("diagnose", diagnose_node)
    builder.add_node("propose", propose_node)
    builder.add_node("policy_check", policy_check_node)
    builder.add_node("await_approval", await_approval_node)
    builder.add_node("execute_or_reject", execute_or_reject_node)
    builder.add_node("record", record_node)

    # Add edges strictly connecting the nodes sequentially
    builder.add_edge(START, "ingest_alert")
    builder.add_edge("ingest_alert", "check_limits")
    builder.add_edge("check_limits", "diagnose")
    builder.add_edge("diagnose", "propose")
    builder.add_edge("propose", "policy_check")
    builder.add_edge("policy_check", "await_approval")
    builder.add_edge("await_approval", "execute_or_reject")
    builder.add_edge("execute_or_reject", "record")
    builder.add_edge("record", END)

    interrupt_list = ["await_approval"] if interrupt_for_approval else None
    effective_checkpointer = checkpointer or create_sqlite_checkpointer(":memory:")
    return builder.compile(checkpointer=effective_checkpointer, interrupt_before=interrupt_list)
