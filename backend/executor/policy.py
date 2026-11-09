"""Remediation policy engine and validation table.

Purpose: Loads policy rules from config/policy.yaml and validates (cause, action) pairs.
Inputs: DiagnosisCause and RemediationAction enums or string names.
Outputs: Boolean allowance status and allowed action lists.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from backend.agents.models import DiagnosisCause, RemediationAction

DEFAULT_POLICY_PATH = Path("config/policy.yaml")


class PolicyEngine:
    """Enforces policy table constraints mapping causes to permitted actions."""

    def __init__(self, table: dict[str, list[str]]) -> None:
        self._table: dict[str, set[str]] = {
            cause.lower(): {act.lower() for act in actions} for cause, actions in table.items()
        }

    @classmethod
    def load(cls, path: Path | str = DEFAULT_POLICY_PATH) -> PolicyEngine:
        """Load policy mappings from a YAML configuration file."""
        policy_file = Path(path)
        if not policy_file.exists():
            raise FileNotFoundError(f"Policy configuration file not found at {policy_file}")

        content = policy_file.read_text(encoding="utf-8")
        raw_data: Any = yaml.safe_load(content)
        if not isinstance(raw_data, dict):
            raise ValueError(f"Invalid policy YAML format in {policy_file}: expected dictionary")

        table: dict[str, list[str]] = {}
        for cause_key, actions_val in raw_data.items():
            if not isinstance(actions_val, list):
                raise ValueError(f"Invalid actions list for cause '{cause_key}' in {policy_file}")
            table[str(cause_key)] = [str(a) for a in actions_val]

        return cls(table)

    def is_allowed(
        self,
        cause: DiagnosisCause | str,
        action: RemediationAction | str,
    ) -> bool:
        """Determine whether an action is authorized for a given diagnosis cause (SEC-43)."""
        cause_str = cause.value.lower() if isinstance(cause, DiagnosisCause) else str(cause).lower()
        action_str = (
            action.value.lower() if isinstance(action, RemediationAction) else str(action).lower()
        )

        allowed_actions = self._table.get(cause_str)
        if allowed_actions is None:
            return False

        return action_str in allowed_actions

    def get_allowed_actions(self, cause: DiagnosisCause | str) -> list[RemediationAction]:
        """Return the list of permitted RemediationAction enums for a cause."""
        cause_str = cause.value.lower() if isinstance(cause, DiagnosisCause) else str(cause).lower()
        action_strings = self._table.get(cause_str, set())
        result: list[RemediationAction] = []
        for act in RemediationAction:
            if act.value.lower() in action_strings:
                result.append(act)
        return result
