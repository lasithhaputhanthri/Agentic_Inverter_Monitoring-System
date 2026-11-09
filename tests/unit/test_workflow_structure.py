"""Structural tests for the incident response workflow graph.

Purpose: Verifies that walking the workflow StateGraph proves no path exists from propose
         to execute_or_reject that skips await_approval.
Inputs: Compiled StateGraph instance.
Outputs: Pytest assertions on graph topology and path invariants.
"""

from __future__ import annotations

from unittest.mock import MagicMock

from backend.agents.diagnosis import DiagnosisAgent
from backend.agents.remediation import RemediationAgent
from backend.executor.executor import IsolatedExecutor
from backend.executor.policy import PolicyEngine
from backend.workflow.approval import ApprovalStore
from backend.workflow.graph import build_incident_workflow


def test_no_path_from_propose_to_execute_skips_await_approval() -> None:
    """Acceptance test: Walking the graph shows no path from propose to execute_or_reject skipping await_approval."""
    workflow = build_incident_workflow(
        diagnosis_agent=MagicMock(spec=DiagnosisAgent),
        remediation_agent=MagicMock(spec=RemediationAgent),
        policy_engine=MagicMock(spec=PolicyEngine),
        executor=MagicMock(spec=IsolatedExecutor),
        approval_store=MagicMock(spec=ApprovalStore),
        interrupt_for_approval=False,
    )

    raw_graph = workflow.get_graph()
    adjacency: dict[str, list[str]] = {}
    for edge in raw_graph.edges:
        adjacency.setdefault(edge.source, []).append(edge.target)

    # Find all simple paths from 'propose' to 'execute_or_reject'
    def find_all_paths(current: str, target: str, visited: set[str]) -> list[list[str]]:
        if current == target:
            return [[target]]
        paths: list[list[str]] = []
        for nxt in adjacency.get(current, []):
            if nxt not in visited:
                subpaths = find_all_paths(nxt, target, visited | {nxt})
                for sp in subpaths:
                    paths.append([current] + sp)
        return paths

    paths = find_all_paths("propose", "execute_or_reject", {"propose"})

    assert len(paths) > 0, "There must be at least one path from propose to execute_or_reject"

    for path in paths:
        assert "await_approval" in path, (
            f"Invariant violation: path {path} reaches execute_or_reject without await_approval"
        )
        assert path.index("await_approval") < path.index("execute_or_reject")
