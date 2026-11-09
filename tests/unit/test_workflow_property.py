"""Property-based verification of the approval gate invariant.

Purpose: Acceptance test: Over 500 random alerts with random agent outputs,
         proves zero executions happen without a valid, unexpired approval record.
Inputs: Random generator seeds, simulated alert streams, randomized agent outputs.
Outputs: Pytest assertion that unapproved executions == 0 across all 500 iterations.
"""

from __future__ import annotations

import random
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

from backend.agents.models import ActionProposal, DiagnosisCause, DiagnosisResult, RemediationAction
from backend.executor.executor import IsolatedExecutor
from backend.executor.policy import PolicyEngine
from backend.monitor.models import Alert, AlertSeverity, MonitorRule
from backend.workflow.approval import ApprovalDecision, ApprovalStore


class MockSimulatorStateAPI:
    """In-memory mock for SimulatorStateAPI."""

    def __init__(self, fleet_size: int = 20) -> None:
        self.device_ids = {f"INV-{i:02d}" for i in range(1, fleet_size + 1)}
        self.states: dict[str, dict[str, Any]] = {d: {} for d in self.device_ids}
        self.notes: dict[str, list[str]] = {d: [] for d in self.device_ids}

    def has_device(self, device_id: str) -> bool:
        return device_id in self.device_ids

    def update_device_state(self, device_id: str, updates: dict[str, Any]) -> None:
        self.states[device_id].update(updates)

    def append_maintenance_note(self, device_id: str, note: str) -> None:
        self.notes[device_id].append(note)

    def get_device_state(self, device_id: str) -> dict[str, Any]:
        return dict(self.states[device_id])


def test_zero_executions_without_approval_property_500_runs() -> None:
    """Acceptance test: Over 500 random iterations, zero executions happen without valid approval."""
    rng = random.Random(1337)
    policy = PolicyEngine.load("config/policy.yaml")
    sim_api = MockSimulatorStateAPI(fleet_size=20)
    approval_store = ApprovalStore()
    executor = IsolatedExecutor(
        simulator_api=sim_api,
        policy_engine=policy,
        approval_store=approval_store,
    )

    base_time = datetime(2026, 6, 1, 12, 0, 0, tzinfo=UTC)
    unapproved_executions_count = 0
    total_executions_count = 0

    rules: list[MonitorRule] = list(MonitorRule)
    causes: list[DiagnosisCause] = list(DiagnosisCause)
    actions: list[RemediationAction] = list(RemediationAction)

    for i in range(500):
        now = base_time + timedelta(hours=i * 2)  # Space out by 2 hours so device rate limits reset
        dev_id = f"INV-{rng.randint(1, 20):02d}"
        rule = rng.choice(rules)
        alert = Alert.create(
            device_id=dev_id,
            ts=now,
            rule=rule,
            severity=AlertSeverity.WARNING,
            observed=100.0,
            threshold=50.0,
        )

        cause = rng.choice(causes)
        diagnosis = DiagnosisResult(
            device_id=dev_id,
            cause=cause,
            confidence=round(rng.uniform(0.5, 0.99), 2),
            evidence=[f"Evidence for {cause.value}"],
            prompt_version="v1",
            model="fake-llm",
        )

        action = rng.choice(actions)
        prop_uuid = uuid4()
        prop_str = str(prop_uuid)
        # Occasionally test spoofed device mismatch (SEC-33)
        prop_dev = dev_id if rng.random() > 0.1 else f"INV-{rng.randint(1, 20):02d}"
        proposal = ActionProposal(
            proposal_id=prop_uuid,
            device_id=prop_dev,
            action=action,
            justification=f"Justification for {action.value}",
            diagnosis_ref=diagnosis.cause.value,
            prompt_version="v1",
            model="fake-llm",
        )

        # Decide whether this proposal gets approved, rejected, expired, or left unapproved
        scenario = rng.choice(["approve", "reject", "expired", "unapproved"])
        if scenario == "approve":
            approval_store.record_decision(
                proposal_id=prop_str,
                approver_id="test_admin",
                decision=ApprovalDecision.APPROVE,
                reason="Looks good",
                timestamp=now - timedelta(minutes=5),  # Fresh (5 mins old)
            )
        elif scenario == "reject":
            approval_store.record_decision(
                proposal_id=prop_str,
                approver_id="test_admin",
                decision=ApprovalDecision.REJECT,
                reason="Unsafe",
                timestamp=now - timedelta(minutes=5),
            )
        elif scenario == "expired":
            approval_store.record_decision(
                proposal_id=prop_str,
                approver_id="test_admin",
                decision=ApprovalDecision.APPROVE,
                reason="Approved but timed out",
                timestamp=now - timedelta(minutes=35),  # Expired (> 30 mins)
            )
        # scenario == "unapproved" -> no entry in approval_store

        result = executor.execute(proposal, diagnosis, alert, current_time=now)

        if result.executed:
            total_executions_count += 1
            # Check invariant: Must have had an unexpired APPROVE record
            app_rec = approval_store.get_decision(prop_str)
            if (
                app_rec is None
                or app_rec.decision != ApprovalDecision.APPROVE
                or app_rec.is_expired(now)
            ):
                unapproved_executions_count += 1

    assert unapproved_executions_count == 0, (
        f"Security breach: {unapproved_executions_count} unapproved executions occurred!"
    )
    assert total_executions_count > 0, "At least some valid approved actions should have executed"
    print(
        f"\nProperty test passed: 500 runs, {total_executions_count} executed, 0 unapproved executions."
    )
