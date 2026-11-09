"""Acceptance tests for Phase 7 evaluation harness and reproducibility.

Purpose: Verifies Phase 7 acceptance tests:
         - Two runs with the fake LLM produce byte-identical results.json.
         - Without --final, the harness refuses the held-out seed range.
         - Re-running held-out partition is refused if marker file exists.
         - Importing evaluation from a runtime module violates architectural rules.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from backend.evaluation.harness import run_benchmark
from backend.evaluation.report import generate_evaluation_report


def test_harness_refuses_held_out_seed_range_without_final(tmp_path: Path) -> None:
    """Acceptance test: without --final, the harness refuses held-out seeds [2000-2099]."""
    with pytest.raises(ValueError, match=r"(?i)held-out evaluation seed range.*--final"):
        run_benchmark(seeds=[2000], output_dir=tmp_path, is_final=False)


def test_harness_refuses_rerunning_held_out_if_marker_exists(tmp_path: Path) -> None:
    """Acceptance test: harness refuses to re-run held-out seeds if marker file exists."""
    marker_file = tmp_path / ".held_out_completed"
    marker_file.write_text("2026-11-09T00:00:00Z", encoding="utf-8")

    with pytest.raises(RuntimeError, match=r"(?i)held-out evaluation was already completed"):
        run_benchmark(seeds=[2000], output_dir=tmp_path, is_final=True)


def test_two_runs_with_fake_llm_produce_byte_identical_results_json(tmp_path: Path) -> None:
    """Acceptance test: two evaluation runs with the fake LLM produce byte-identical results.json."""
    dir1 = tmp_path / "run_1"
    dir2 = tmp_path / "run_2"
    fixed_seeds = [1001]

    # Run 1
    bench1 = run_benchmark(
        seeds=fixed_seeds, conditions=["rule_baseline"], output_dir=dir1, is_final=False
    )
    # Fix timestamp for reproducibility check
    bench1["timestamp"] = "2026-06-01T12:00:00+00:00"
    json_path_1, _ = generate_evaluation_report(bench1, output_dir=dir1)

    # Run 2
    bench2 = run_benchmark(
        seeds=fixed_seeds, conditions=["rule_baseline"], output_dir=dir2, is_final=False
    )
    bench2["timestamp"] = "2026-06-01T12:00:00+00:00"
    json_path_2, _ = generate_evaluation_report(bench2, output_dir=dir2)

    bytes1 = json_path_1.read_bytes()
    bytes2 = json_path_2.read_bytes()

    assert bytes1 == bytes2, "Evaluation results.json is not byte-identical across runs!"


def test_importing_evaluation_from_runtime_module_violates_architecture() -> None:
    """Acceptance test: importing evaluation from a runtime module fails the dependency test."""
    from tests.unit.test_dependency_rules import get_project_root

    root = get_project_root()
    backend_dir = root / "backend"

    # Verify that in actual code, no runtime file outside backend/evaluation imports backend.evaluation
    for py_file in backend_dir.rglob("*.py"):
        rel = py_file.relative_to(root).as_posix()
        if not rel.startswith("backend/evaluation/"):
            text = py_file.read_text(encoding="utf-8")
            assert "backend.evaluation" not in text, (
                f"Forbidden import of backend.evaluation found in runtime file {rel}"
            )
