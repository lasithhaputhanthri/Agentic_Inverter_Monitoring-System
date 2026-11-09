"""Unit tests for the isolated remediation executor.

Purpose: Verifies executor gates: unknown device rejection (SEC-40), device mismatch rejection (SEC-33),
         idempotency on repeated execution key (SEC-42), and device-level hourly rate limiting.
Inputs: ActionProposal, DiagnosisResult, Alert, and MockSimulatorStateAPI.
Outputs: Pytest assertions on ExecutionResult status and simulator state mutations.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

import pytest
from backend.agents.models import ActionProposal, DiagnosisCause, DiagnosisResult, RemediationAction
from backend.executor.executor import IsolatedExecutor
from backend.executor.policy import PolicyEngine
from backend.monitor.models import Alert, AlertSeverity, MonitorRule
from backend.workflow.approval import ApprovalDecision, ApprovalStore
from backend.workflow.audit import AuditEventType, InMemoryAuditSink


class MockSimulatorStateAPI:
    """In-memory mock implementing SimulatorStateAPI."""

    def __init__(self, fleet: list[str]) -> None:
        self.fleet = set(fleet)
        self.states: dict[str, dict[str, Any]] = {d: {} for d in fleet}
        self.notes: dict[str, list[str]] = {d: [] for d in fleet}

    def has_device(self, device_id: str) -> bool:
        return device_id in self.fleet

    def update_device_state(self, device_id: str, updates: dict[str, Any]) -> None:
        if device_id not in self.fleet:
            raise KeyError(device_id)
        self.states[device_id].update(updates)

    def append_maintenance_note(self, device_id: str, note: str) -> None:
        if device_id not in self.fleet:
            raise KeyError(device_id)
        self.notes[device_id].append(note)

    def get_device_state(self, device_id: str) -> dict[str, Any]:
        return dict(self.states[device_id])


@pytest.fixture
def sim_api() -> MockSimulatorStateAPI:
    return MockSimulatorStateAPI([f"INV-{i:02d}" for i in range(1, 21)])


@pytest.fixture
def policy() -> PolicyEngine:
    return PolicyEngine.load("config/policy.yaml")


@pytest.fixture
def setup_executor(
    sim_api: MockSimulatorStateAPI, policy: PolicyEngine
) -> tuple[IsolatedExecutor, ApprovalStore, InMemoryAuditSink]:
    approvals = ApprovalStore()
    audit = InMemoryAuditSink()
    executor = IsolatedExecutor(
        simulator_api=sim_api,
        policy_engine=policy,
        approval_store=approvals,
        audit_sink=audit,
    )
    return executor, approvals, audit


def test_executor_refuses_unknown_device(
    setup_executor: tuple[IsolatedExecutor, ApprovalStore, InMemoryAuditSink],
) -> None:
    """Acceptance test: Actions on devices not in simulator registry are refused (SEC-40)."""
    executor, approvals, audit = setup_executor
    now = datetime(2026, 6, 1, 12, 0, 0, tzinfo=UTC)

    alert = Alert.create(
        "INV-99", now, MonitorRule.GRID_VOLTAGE_LOW, AlertSeverity.WARNING, 195.0, 207.0
    )
    diag = DiagnosisResult(
        device_id="INV-99",
        cause=DiagnosisCause.GRID_SAG,
        confidence=0.9,
        evidence=["Voltage drop"],
        prompt_version="v1",
        model="fake-llm",
    )
    prop = ActionProposal(
        proposal_id=uuid4(),
        device_id="INV-99",
        action=RemediationAction.SCHEDULE_INSPECTION,
        justification="Inspect grid inverter",
        diagnosis_ref="grid_sag",
        prompt_version="v1",
        model="fake-llm",
    )

    approvals.record_decision(
        str(prop.proposal_id), "admin", ApprovalDecision.APPROVE, timestamp=now
    )

    res = executor.execute(prop, diag, alert, current_time=now)
    assert not res.executed
    assert res.status == "refused"
    assert res.reason == "unknown_device"

    refusal_events = audit.get_events_by_type(AuditEventType.EXECUTION_REFUSED)
    assert len(refusal_events) == 1
    assert refusal_events[0].payload["reason"] == "unknown_device"


def test_executor_refuses_device_mismatch(
    setup_executor: tuple[IsolatedExecutor, ApprovalStore, InMemoryAuditSink],
) -> None:
    """Acceptance test: Proposal device differing from alert device is strictly refused (SEC-33)."""
    executor, approvals, audit = setup_executor
    now = datetime(2026, 6, 1, 12, 0, 0, tzinfo=UTC)

    alert = Alert.create(
        "INV-01", now, MonitorRule.TEMP_HIGH_FOR_POWER, AlertSeverity.WARNING, 65.0, 12.0
    )
    diag = DiagnosisResult(
        device_id="INV-01",
        cause=DiagnosisCause.OVERHEATING,
        confidence=0.9,
        evidence=["Thermal high"],
        prompt_version="v1",
        model="fake-llm",
    )
    # Spoofed device INV-02
    prop = ActionProposal(
        proposal_id=uuid4(),
        device_id="INV-02",
        action=RemediationAction.REDUCE_LOAD,
        justification="Reduce load",
        diagnosis_ref="overheating",
        prompt_version="v1",
        model="fake-llm",
    )

    approvals.record_decision(
        str(prop.proposal_id), "admin", ApprovalDecision.APPROVE, timestamp=now
    )

    res = executor.execute(prop, diag, alert, current_time=now)
    assert not res.executed
    assert res.status == "refused"
    assert res.reason == "device_mismatch"


def test_executor_idempotency_duplicate_execution_key_is_noop(
    setup_executor: tuple[IsolatedExecutor, ApprovalStore, InMemoryAuditSink],
    sim_api: MockSimulatorStateAPI,
) -> None:
    """Acceptance test: Repeated execution key returns stored result and changes nothing (SEC-42)."""
    executor, approvals, audit = setup_executor
    now = datetime(2026, 6, 1, 12, 0, 0, tzinfo=UTC)

    alert = Alert.create(
        "INV-01", now, MonitorRule.TEMP_HIGH_FOR_POWER, AlertSeverity.WARNING, 65.0, 12.0
    )
    diag = DiagnosisResult(
        device_id="INV-01",
        cause=DiagnosisCause.OVERHEATING,
        confidence=0.9,
        evidence=["Thermal high"],
        prompt_version="v1",
        model="fake-llm",
    )
    prop = ActionProposal(
        proposal_id=uuid4(),
        device_id="INV-01",
        action=RemediationAction.REDUCE_LOAD,
        justification="Reduce load scale",
        diagnosis_ref="overheating",
        prompt_version="v1",
        model="fake-llm",
    )

    approvals.record_decision(
        str(prop.proposal_id), "admin", ApprovalDecision.APPROVE, timestamp=now
    )

    # First execution: succeeds
    res1 = executor.execute(prop, diag, alert, current_time=now)
    assert res1.executed
    assert res1.status == "executed"
    assert sim_api.get_device_state("INV-01")["load_scale"] == 0.7

    # Mutate simulator state externally to test if duplicate call touches state
    sim_api.update_device_state("INV-01", {"load_scale": 0.5})

    # Second execution with identical proposal ID (key)
    res2 = executor.execute(prop, diag, alert, current_time=now + timedelta(minutes=5))
    assert res2 == res1
    # State was NOT changed back to 0.7; it remained 0.5 because it was a pure no-op
    assert sim_api.get_device_state("INV-01")["load_scale"] == 0.5

    # Audit logged exactly 1 executed event
    executed_events = audit.get_events_by_type(AuditEventType.EXECUTED)
    assert len(executed_events) == 1


def test_executor_rate_limit_blocks_second_action_within_hour(
    setup_executor: tuple[IsolatedExecutor, ApprovalStore, InMemoryAuditSink],
) -> None:
    """Acceptance test: Device rate limit (1 action per device per hour) blocks second action."""
    executor, approvals, audit = setup_executor
    now = datetime(2026, 6, 1, 12, 0, 0, tzinfo=UTC)

    alert1 = Alert.create(
        "INV-03", now, MonitorRule.TEMP_HIGH_FOR_POWER, AlertSeverity.WARNING, 65.0, 12.0
    )
    diag1 = DiagnosisResult(
        device_id="INV-03",
        cause=DiagnosisCause.OVERHEATING,
        confidence=0.9,
        evidence=["Thermal high"],
        prompt_version="v1",
        model="fake-llm",
    )
    prop1 = ActionProposal(
        proposal_id=uuid4(),
        device_id="INV-03",
        action=RemediationAction.REDUCE_LOAD,
        justification="Reduce load",
        diagnosis_ref="overheating",
        prompt_version="v1",
        model="fake-llm",
    )

    approvals.record_decision(
        str(prop1.proposal_id), "admin", ApprovalDecision.APPROVE, timestamp=now
    )
    res1 = executor.execute(prop1, diag1, alert1, current_time=now)
    assert res1.executed

    # Second distinct proposal for same device only 15 minutes later
    prop2 = ActionProposal(
        proposal_id=uuid4(),
        device_id="INV-03",
        action=RemediationAction.SCHEDULE_INSPECTION,
        justification="Inspection note",
        diagnosis_ref="overheating",
        prompt_version="v1",
        model="fake-llm",
    )
    approvals.record_decision(
        str(prop2.proposal_id),
        "admin",
        ApprovalDecision.APPROVE,
        timestamp=now + timedelta(minutes=15),
    )

    res2 = executor.execute(prop2, diag1, alert1, current_time=now + timedelta(minutes=15))
    assert not res2.executed
    assert res2.status == "refused"
    assert res2.reason == "rate_limit_exceeded"

    # After 61 minutes, third distinct proposal for same device succeeds
    prop3 = ActionProposal(
        proposal_id=uuid4(),
        device_id="INV-03",
        action=RemediationAction.SCHEDULE_INSPECTION,
        justification="Follow-up inspection",
        diagnosis_ref="overheating",
        prompt_version="v1",
        model="fake-llm",
    )
    approvals.record_decision(
        str(prop3.proposal_id),
        "admin",
        ApprovalDecision.APPROVE,
        timestamp=now + timedelta(minutes=61),
    )

    res3 = executor.execute(prop3, diag1, alert1, current_time=now + timedelta(minutes=61))
    assert res3.executed
    assert res3.status == "executed"
