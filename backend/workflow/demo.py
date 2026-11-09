"""Demo runner for Phase 5 end-to-end incident response flow.

Purpose: Executes one complete incident lifecycle from alert through approval to execution,
         recording the append-only audit trail and generating docs/demo/phase5_audit.txt.
Inputs: Monitor alert, fake LLM responses, operator approval input.
Outputs: Formatted audit trail saved to docs/demo/phase5_audit.txt without site data.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from langchain_core.runnables import RunnableConfig

from backend.agents.diagnosis import DiagnosisAgent
from backend.agents.llm_client import FakeLLMClient
from backend.agents.models import DiagnosisCause, RemediationAction
from backend.agents.remediation import RemediationAgent
from backend.common.prompts import ask_decision
from backend.executor.executor import IsolatedExecutor
from backend.executor.policy import PolicyEngine
from backend.monitor.models import Alert, AlertSeverity, MonitorRule
from backend.workflow.approval import ApprovalDecision, ApprovalStore
from backend.workflow.audit import AuditEvent, InMemoryAuditSink
from backend.workflow.graph import build_incident_workflow

DEMO_OUTPUT_FILE = Path("docs/demo/phase5_audit.txt")


class DemoSimulatorAPI:
    """Simulator state API implementation for the demo run."""

    def __init__(self) -> None:
        self._states: dict[str, dict[str, Any]] = {"INV-01": {}}
        self._notes: dict[str, list[str]] = {"INV-01": []}

    def has_device(self, device_id: str) -> bool:
        return device_id in self._states

    def update_device_state(self, device_id: str, updates: dict[str, Any]) -> None:
        self._states[device_id].update(updates)

    def append_maintenance_note(self, device_id: str, note: str) -> None:
        self._notes[device_id].append(note)

    def get_device_state(self, device_id: str) -> dict[str, Any]:
        return dict(self._states[device_id])


def run_phase5_demo(output_path: Path = DEMO_OUTPUT_FILE) -> list[AuditEvent]:
    """Execute complete alert -> diagnosis -> proposal -> approval -> execution demo."""
    # Setup simulated incident
    now = datetime(2026, 6, 1, 14, 30, 0, tzinfo=UTC)
    alert = Alert.create(
        device_id="INV-01",
        ts=now,
        rule=MonitorRule.TEMP_HIGH_FOR_POWER,
        severity=AlertSeverity.WARNING,
        observed=67.8,
        threshold=12.0,
    )

    fake_client = FakeLLMClient()
    fake_client.queue_response(
        json.dumps(
            {
                "cause": DiagnosisCause.OVERHEATING.value,
                "confidence": 0.94,
                "evidence": ["Inverter temperature 67.8C exceeds expected curve by 12.0C"],
            }
        )
    )
    fake_client.queue_response(
        json.dumps(
            {
                "action": RemediationAction.REDUCE_LOAD.value,
                "justification": "Derate output to 70% to cool inverter without tripping safety breaker",
            }
        )
    )

    diag_agent = DiagnosisAgent(client=fake_client)
    rem_agent = RemediationAgent(client=fake_client)
    policy = PolicyEngine.load("config/policy.yaml")
    sim_api = DemoSimulatorAPI()
    approval_store = ApprovalStore()
    audit_sink = InMemoryAuditSink()

    executor = IsolatedExecutor(
        simulator_api=sim_api,
        policy_engine=policy,
        approval_store=approval_store,
        audit_sink=audit_sink,
    )

    workflow = build_incident_workflow(
        diagnosis_agent=diag_agent,
        remediation_agent=rem_agent,
        policy_engine=policy,
        executor=executor,
        approval_store=approval_store,
        audit_sink=audit_sink,
        interrupt_for_approval=True,
    )

    config: RunnableConfig = {"configurable": {"thread_id": str(alert.alert_id)}}

    # Phase A: Workflow runs up to await_approval interrupt
    workflow.invoke(
        {"alert": alert, "telemetry": [], "snapshot": {}, "current_time": now},
        config=config,
    )

    # Phase B: Operator review and decision using ask_decision mock input
    state_paused = workflow.get_state(config)
    proposal = state_paused.values["proposal"]
    diagnosis = state_paused.values["diagnosis"]
    assert proposal is not None and diagnosis is not None

    def mock_operator_input(prompt_text: str) -> str:
        if "Decision" in prompt_text:
            return "approve"
        return "Verified thermal condition; approved 70% derate"

    decision_str, reason, operator = ask_decision(
        proposal=proposal,
        diagnosis=diagnosis,
        alert=alert,
        operator_name="lead_operator_01",
        input_fn=mock_operator_input,
    )

    approval_rec = approval_store.record_decision(
        proposal_id=str(proposal.proposal_id),
        approver_id=operator,
        decision=ApprovalDecision(decision_str),
        reason=reason,
        timestamp=now + timedelta(minutes=1),
    )

    # Phase C: Update workflow state with approval and resume execution
    workflow.update_state(config, {"approval": approval_rec})
    workflow.invoke(None, config=config)

    # Format audit log output (sanitized IDs and enums, no site data)
    output_lines = [
        "# Incident Response Workflow Phase 5 Audit Log",
        f"# Incident Thread: {alert.alert_id}",
        f"# Generated: {now.isoformat()}",
        "# " + "-" * 70,
    ]
    for ev in audit_sink.events:
        payload_str = ", ".join(f"{k}={v}" for k, v in sorted(ev.payload.items()))
        output_lines.append(
            f"[{ev.timestamp.isoformat()}] {ev.event_id} {ev.event_type.value}: {payload_str}"
        )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(output_lines) + "\n", encoding="utf-8")

    return audit_sink.events


if __name__ == "__main__":
    run_phase5_demo()
