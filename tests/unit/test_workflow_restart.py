"""Acceptance test for workflow checkpointing and restart resilience.

Purpose: Verifies acceptance criteria: Stop at await_approval, create a new graph
         with the same SQLite checkpointer, and resume with the approval to completion.
Inputs: Alert, FakeLLMClient, SQLite persistent checkpointer file.
Outputs: Pytest assertion that restarted workflow successfully executes and finalizes.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from backend.agents.diagnosis import DiagnosisAgent
from backend.agents.llm_client import FakeLLMClient
from backend.agents.models import DiagnosisCause, RemediationAction
from backend.agents.remediation import RemediationAgent
from backend.executor.executor import IsolatedExecutor
from backend.executor.policy import PolicyEngine
from backend.monitor.models import Alert, AlertSeverity, MonitorRule
from backend.workflow.approval import ApprovalDecision, ApprovalStore
from backend.workflow.audit import InMemoryAuditSink
from backend.workflow.graph import build_incident_workflow
from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.sqlite import SqliteSaver


class MockSimulatorStateAPI:
    """Mock SimulatorStateAPI."""

    def __init__(self) -> None:
        self.device = "INV-01"
        self.state: dict[str, Any] = {}
        self.notes: list[str] = []

    def has_device(self, device_id: str) -> bool:
        return device_id == self.device

    def update_device_state(self, device_id: str, updates: dict[str, Any]) -> None:
        self.state.update(updates)

    def append_maintenance_note(self, device_id: str, note: str) -> None:
        self.notes.append(note)

    def get_device_state(self, device_id: str) -> dict[str, Any]:
        return dict(self.state)


def test_workflow_stop_at_approval_and_resume_on_new_graph_instance(tmp_path: Path) -> None:
    """Acceptance test: Stop at await_approval, recreate graph with same SQLite checkpointer, resume."""
    db_file = tmp_path / "workflow_state.db"
    conn = sqlite3.connect(str(db_file), check_same_thread=False)
    checkpointer = SqliteSaver(conn)

    policy = PolicyEngine.load("config/policy.yaml")
    sim_api = MockSimulatorStateAPI()
    approval_store = ApprovalStore()
    audit_sink = InMemoryAuditSink()

    fake_client = FakeLLMClient()
    # Queue diagnosis response
    fake_client.queue_response(
        json.dumps(
            {
                "cause": DiagnosisCause.OVERHEATING.value,
                "confidence": 0.95,
                "evidence": ["High heat sink temperature under load"],
            }
        )
    )
    # Queue remediation response
    fake_client.queue_response(
        json.dumps(
            {
                "action": RemediationAction.REDUCE_LOAD.value,
                "justification": "Scale load to 0.7 to avoid inverter thermal shutdown",
            }
        )
    )

    diag_agent = DiagnosisAgent(client=fake_client)
    rem_agent = RemediationAgent(client=fake_client)
    executor = IsolatedExecutor(
        simulator_api=sim_api,
        policy_engine=policy,
        approval_store=approval_store,
        audit_sink=audit_sink,
    )

    # 1. Build initial workflow instance with interrupt at await_approval
    workflow_1 = build_incident_workflow(
        diagnosis_agent=diag_agent,
        remediation_agent=rem_agent,
        policy_engine=policy,
        executor=executor,
        approval_store=approval_store,
        audit_sink=audit_sink,
        checkpointer=checkpointer,
        interrupt_for_approval=True,
    )

    now = datetime(2026, 6, 1, 12, 0, 0, tzinfo=UTC)
    alert = Alert.create(
        "INV-01", now, MonitorRule.TEMP_HIGH_FOR_POWER, AlertSeverity.WARNING, 68.0, 12.0
    )
    config: RunnableConfig = {"configurable": {"thread_id": str(alert.alert_id)}}

    # Execute workflow 1 -> pauses right before await_approval
    _ = workflow_1.invoke(
        {"alert": alert, "telemetry": [], "snapshot": {}},
        config=config,
    )

    # Verify workflow stopped at await_approval
    checkpoint_state = workflow_1.get_state(config)
    assert checkpoint_state.next == ("await_approval",)
    assert checkpoint_state.values["status"] == "awaiting_approval"
    proposal = checkpoint_state.values["proposal"]
    assert proposal is not None
    assert proposal.action == RemediationAction.REDUCE_LOAD

    # State has NOT executed yet
    assert "load_scale" not in sim_api.get_device_state("INV-01")

    # 2. Simulate process restart: Discard workflow_1 completely and instantiate workflow_2
    del workflow_1

    # Connect to the same SQLite database file
    conn2 = sqlite3.connect(str(db_file), check_same_thread=False)
    checkpointer2 = SqliteSaver(conn2)

    workflow_2 = build_incident_workflow(
        diagnosis_agent=diag_agent,
        remediation_agent=rem_agent,
        policy_engine=policy,
        executor=executor,
        approval_store=approval_store,
        audit_sink=audit_sink,
        checkpointer=checkpointer2,
        interrupt_for_approval=True,
    )

    # Verify workflow_2 restored the paused state from SQLite
    restored_state = workflow_2.get_state(config)
    assert restored_state.next == ("await_approval",)
    assert restored_state.values["proposal"].proposal_id == proposal.proposal_id

    # 3. Operator reviews and records approval
    approval_rec = approval_store.record_decision(
        proposal_id=str(proposal.proposal_id),
        approver_id="chief_operator",
        decision=ApprovalDecision.APPROVE,
        reason="Approved thermal derating",
        timestamp=now + timedelta(minutes=2),
    )

    # Update workflow state with the approval
    workflow_2.update_state(config, {"approval": approval_rec})

    # 4. Resume execution on workflow_2
    final_state = workflow_2.invoke(None, config=config)

    # Verify execution completed on simulator state
    assert final_state["status"] == "completed"
    assert final_state["execution_result"]["executed"] is True
    assert sim_api.get_device_state("INV-01")["load_scale"] == 0.7

    # Clean up SQLite connections for Windows file handle cleanup
    conn.close()
    conn2.close()
