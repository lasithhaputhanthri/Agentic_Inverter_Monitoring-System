"""Tests verifying complete architectural isolation of the operator dashboard.

Purpose: Verifies Phase 6 acceptance test:
         - "The dashboard has no import of simulator, faults, executor, or storage."
"""

from __future__ import annotations

import ast
from pathlib import Path


def test_dashboard_has_no_forbidden_imports() -> None:
    root = Path(__file__).resolve().parents[2]
    dashboard_files = [
        root / "frontend" / "dashboard" / "app.py",
        root / "backend" / "dashboard" / "app.py",
    ]

    forbidden_tokens = ["simulator", "faults", "executor", "storage"]

    for dash_file in dashboard_files:
        assert dash_file.exists(), f"Dashboard file {dash_file} not found"
        tree = ast.parse(dash_file.read_text(encoding="utf-8"), filename=str(dash_file))

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    for forbidden in forbidden_tokens:
                        assert forbidden not in alias.name, (
                            f"Forbidden import '{alias.name}' detected in {dash_file.name}:{node.lineno}"
                        )
            elif isinstance(node, ast.ImportFrom):
                module = node.module or ""
                for forbidden in forbidden_tokens:
                    assert forbidden not in module, (
                        f"Forbidden from-import '{module}' detected in {dash_file.name}:{node.lineno}"
                    )
