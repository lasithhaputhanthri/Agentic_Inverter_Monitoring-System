"""Unit tests for remediation policy table validation.

Purpose: Verifies SEC-43 compliance: Allowed pairs succeed, disallowed pairs are blocked,
         specifically reset_relay on grid_sag is strictly forbidden.
Inputs: DiagnosisCause and RemediationAction pairs.
Outputs: Pytest assertions on policy allowance and rejection rules.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from backend.agents.models import DiagnosisCause, RemediationAction
from backend.executor.policy import PolicyEngine


@pytest.fixture
def policy_engine() -> PolicyEngine:
    return PolicyEngine.load("config/policy.yaml")


def test_policy_engine_loads_from_yaml(policy_engine: PolicyEngine) -> None:
    """Acceptance test: Policy loads successfully from config/policy.yaml."""
    assert Path("config/policy.yaml").exists()
    assert policy_engine is not None


def test_policy_blocks_reset_relay_for_grid_sag(policy_engine: PolicyEngine) -> None:
    """Acceptance test: reset_relay for grid_sag is strictly blocked (SEC-43)."""
    allowed = policy_engine.is_allowed(DiagnosisCause.GRID_SAG, RemediationAction.RESET_RELAY)
    assert not allowed, "Critical safety violation: reset_relay must be blocked for grid_sag"


def test_policy_allows_permitted_pairs(policy_engine: PolicyEngine) -> None:
    """Acceptance test: Allowed pairs from config/policy.yaml succeed."""
    # overheating
    assert policy_engine.is_allowed(DiagnosisCause.OVERHEATING, RemediationAction.REDUCE_LOAD)
    assert policy_engine.is_allowed(
        DiagnosisCause.OVERHEATING, RemediationAction.SCHEDULE_INSPECTION
    )
    assert policy_engine.is_allowed(DiagnosisCause.OVERHEATING, RemediationAction.NO_ACTION)

    # grid_sag
    assert policy_engine.is_allowed(DiagnosisCause.GRID_SAG, RemediationAction.SCHEDULE_INSPECTION)
    assert policy_engine.is_allowed(DiagnosisCause.GRID_SAG, RemediationAction.NO_ACTION)

    # stuck_relay
    assert policy_engine.is_allowed(DiagnosisCause.STUCK_RELAY, RemediationAction.RESET_RELAY)
    assert policy_engine.is_allowed(
        DiagnosisCause.STUCK_RELAY, RemediationAction.SCHEDULE_INSPECTION
    )
    assert policy_engine.is_allowed(DiagnosisCause.STUCK_RELAY, RemediationAction.NO_ACTION)

    # comm_dropout
    assert policy_engine.is_allowed(
        DiagnosisCause.COMM_DROPOUT, RemediationAction.SCHEDULE_INSPECTION
    )
    assert policy_engine.is_allowed(DiagnosisCause.COMM_DROPOUT, RemediationAction.NO_ACTION)

    # unknown
    assert policy_engine.is_allowed(DiagnosisCause.UNKNOWN, RemediationAction.NO_ACTION)
    assert policy_engine.is_allowed(DiagnosisCause.UNKNOWN, RemediationAction.SCHEDULE_INSPECTION)


def test_policy_blocks_unauthorized_pairs(policy_engine: PolicyEngine) -> None:
    """Acceptance test: Any pair not in config/policy.yaml is blocked."""
    assert not policy_engine.is_allowed(DiagnosisCause.GRID_SAG, RemediationAction.REDUCE_LOAD)
    assert not policy_engine.is_allowed(DiagnosisCause.COMM_DROPOUT, RemediationAction.RESET_RELAY)
    assert not policy_engine.is_allowed(DiagnosisCause.COMM_DROPOUT, RemediationAction.REDUCE_LOAD)
    assert not policy_engine.is_allowed(DiagnosisCause.UNKNOWN, RemediationAction.RESET_RELAY)
    assert not policy_engine.is_allowed(DiagnosisCause.UNKNOWN, RemediationAction.REDUCE_LOAD)
