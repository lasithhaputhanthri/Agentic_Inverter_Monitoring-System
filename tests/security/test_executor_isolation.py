"""Security isolation verification for the remediation executor.

Purpose: Verifies SEC-41: The executor operates strictly through the simulator's public state API,
         has no file, socket, or shell access, and does not import prohibited OS/network libraries.
Inputs: MockSimulatorStateAPI, ActionProposal, DiagnosisResult, Alert, and runtime monkeypatches.
Outputs: Pytest assertions that monkeypatching open/socket/subprocess does not affect execution,
         and AST analysis proves no forbidden imports exist.
"""

from __future__ import annotations

import ast
import socket
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from unittest.mock import patch
from uuid import uuid4

from backend.agents.models import ActionProposal, DiagnosisCause, DiagnosisResult, RemediationAction
from backend.executor.executor import IsolatedExecutor
from backend.executor.policy import PolicyEngine
from backend.monitor.models import Alert, AlertSeverity, MonitorRule
from backend.workflow.approval import ApprovalDecision, ApprovalStore


class MockSimulatorStateAPI:
    """Pure in-memory SimulatorStateAPI mock."""

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


def test_executor_succeeds_when_open_socket_subprocess_patched_to_raise() -> None:
    """Acceptance test: Patching open, socket, and subprocess does not prevent remediation execution (SEC-41)."""
    sim_api = MockSimulatorStateAPI()
    policy = PolicyEngine.load("config/policy.yaml")
    approvals = ApprovalStore()
    executor = IsolatedExecutor(
        simulator_api=sim_api,
        policy_engine=policy,
        approval_store=approvals,
    )

    now = datetime(2026, 6, 1, 12, 0, 0, tzinfo=UTC)
    alert = Alert.create(
        "INV-01", now, MonitorRule.TEMP_HIGH_FOR_POWER, AlertSeverity.WARNING, 65.0, 12.0
    )
    diag = DiagnosisResult(
        device_id="INV-01",
        cause=DiagnosisCause.OVERHEATING,
        confidence=0.9,
        evidence=["Thermal reading high"],
        prompt_version="v1",
        model="fake-llm",
    )
    prop = ActionProposal(
        proposal_id=uuid4(),
        device_id="INV-01",
        action=RemediationAction.REDUCE_LOAD,
        justification="Reduce load scale to cool inverter",
        diagnosis_ref="overheating",
        prompt_version="v1",
        model="fake-llm",
    )

    approvals.record_decision(
        str(prop.proposal_id), "admin", ApprovalDecision.APPROVE, timestamp=now
    )

    def forbidden_call(*args: Any, **kwargs: Any) -> Any:
        raise PermissionError(
            "SEC-41 Violation: File, socket, or subprocess access forbidden in executor"
        )

    # Monkeypatch open, socket.socket, and subprocess.Popen / subprocess.run
    with (
        patch("builtins.open", side_effect=forbidden_call),
        patch.object(socket, "socket", side_effect=forbidden_call),
        patch.object(subprocess, "run", side_effect=forbidden_call),
        patch.object(subprocess, "Popen", side_effect=forbidden_call),
    ):
        result = executor.execute(prop, diag, alert, current_time=now)
        assert result.executed
        assert result.status == "executed"
        assert sim_api.get_device_state("INV-01")["load_scale"] == 0.7


def test_executor_ast_contains_no_forbidden_imports() -> None:
    """Acceptance test: AST verification that executor and actions modules import no forbidden modules."""
    forbidden_modules = {"os", "subprocess", "socket", "urllib", "requests", "httpx"}
    target_files = [
        Path("backend/executor/executor.py"),
        Path("backend/executor/actions.py"),
    ]

    for file_path in target_files:
        assert file_path.exists(), f"File {file_path} must exist"
        tree = ast.parse(file_path.read_text(encoding="utf-8"), filename=str(file_path))

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    root_name = alias.name.split(".")[0]
                    assert root_name not in forbidden_modules, (
                        f"SEC-41 Violation: Forbidden import '{alias.name}' found in {file_path}"
                    )

            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    root_name = node.module.split(".")[0]
                    assert root_name not in forbidden_modules, (
                        f"SEC-41 Violation: Forbidden from-import '{node.module}' found in {file_path}"
                    )
