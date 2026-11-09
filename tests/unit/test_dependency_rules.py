"""Dependency direction enforcement tests.

Purpose: Enforces architectural boundaries by analyzing AST imports in src/iir/ and tests/.
Inputs: Python source files under src/iir/ and tests/.
Outputs: Test assertions verifying zero architectural dependency rule violations.
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import NamedTuple


class ImportRecord(NamedTuple):
    source_file: Path
    line: int
    imported_module: str


def collect_imports(base_dir: Path) -> list[ImportRecord]:
    """Parse all python files in base_dir and extract imported modules with line numbers."""
    records: list[ImportRecord] = []
    for py_file in base_dir.rglob("*.py"):
        try:
            tree = ast.parse(py_file.read_text(encoding="utf-8"), filename=str(py_file))
        except SyntaxError:
            continue

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    records.append(
                        ImportRecord(
                            source_file=py_file,
                            line=node.lineno,
                            imported_module=alias.name,
                        )
                    )
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    records.append(
                        ImportRecord(
                            source_file=py_file,
                            line=node.lineno,
                            imported_module=node.module,
                        )
                    )
    return records


def get_project_root() -> Path:
    """Find repository root by locating pyproject.toml."""
    cur = Path(__file__).resolve()
    for parent in cur.parents:
        if (parent / "pyproject.toml").exists():
            return parent
    return Path.cwd()


def test_architecture_dependency_rules() -> None:
    """Validate all architectural dependency constraints for backend and simulator."""
    root = get_project_root()
    backend_dir = root / "backend"
    simulator_dir = root / "simulator"
    tests_dir = root / "tests"

    records = (
        collect_imports(backend_dir) + collect_imports(simulator_dir) + collect_imports(tests_dir)
    )
    violations: list[str] = []

    for rec in records:
        rel_path = rec.source_file.relative_to(root).as_posix()
        imported = rec.imported_module

        # Rule 1: common imports nothing from the project outside backend.common
        if rel_path.startswith("backend/common/"):
            if imported.startswith("backend.") and not imported.startswith("backend.common"):
                violations.append(
                    f"Rule 1 violation in {rel_path}:{rec.line}: common cannot import {imported}"
                )
            if imported.startswith("simulator"):
                violations.append(
                    f"Rule 1 violation in {rel_path}:{rec.line}: common cannot import {imported}"
                )

        # Rule 2: monitor must not import agents, workflow, or faults
        if rel_path.startswith("backend/monitor/"):
            forbidden_monitor: tuple[str, ...] = (
                "backend.agents",
                "backend.workflow",
                "backend.faults",
            )
            if any(imported == f or imported.startswith(f + ".") for f in forbidden_monitor):
                violations.append(
                    f"Rule 2 violation in {rel_path}:{rec.line}: monitor cannot import {imported}"
                )

        # Rule 3: api and dashboard must not import simulator, faults, or executor
        if rel_path.startswith("backend/api/") or rel_path.startswith("backend/dashboard/"):
            forbidden_api: tuple[str, ...] = ("simulator", "backend.faults", "backend.executor")
            if any(imported == f or imported.startswith(f + ".") for f in forbidden_api):
                violations.append(
                    f"Rule 3 violation in {rel_path}:{rec.line}: api/dashboard cannot import {imported}"
                )

        # Rule 4: dashboard must not import storage. It calls the API only.
        if rel_path.startswith("backend/dashboard/"):
            forbidden_dash: tuple[str, ...] = ("backend.storage",)
            if any(imported == f or imported.startswith(f + ".") for f in forbidden_dash):
                violations.append(
                    f"Rule 4 violation in {rel_path}:{rec.line}: dashboard cannot import {imported}"
                )

        # Rule 5: evaluation is imported by nothing at runtime
        if rel_path.startswith("backend/") and not rel_path.startswith("backend/evaluation/"):
            forbidden_eval: tuple[str, ...] = ("backend.evaluation",)
            if any(imported == f or imported.startswith(f + ".") for f in forbidden_eval):
                violations.append(
                    f"Rule 5 violation in {rel_path}:{rec.line}: runtime code cannot import {imported}"
                )

        # Rule 6: Only evaluation and tests may read faults.groundtruth
        if not (rel_path.startswith("backend/evaluation/") or rel_path.startswith("tests/")):
            forbidden_gt: tuple[str, ...] = ("backend.faults.groundtruth",)
            if any(imported == f or imported.startswith(f + ".") for f in forbidden_gt):
                violations.append(
                    f"Rule 6 violation in {rel_path}:{rec.line}: only evaluation/tests may import {imported}"
                )

        # Rule 7: backend runtime modules must not import simulator (decoupled systems)
        if rel_path.startswith("backend/"):
            if imported == "simulator" or imported.startswith("simulator."):
                violations.append(
                    f"Rule 7 violation in {rel_path}:{rec.line}: backend cannot import simulator ({imported})"
                )

    assert not violations, "Architecture dependency violations detected:\n" + "\n".join(violations)
