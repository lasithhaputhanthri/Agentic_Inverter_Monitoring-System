"""Append-only ground truth audit log writer and reader.

Purpose: Persists ground truth records when faults are injected during simulation runs.
Inputs: FaultSpec and injection timestamp.
Outputs: Appended JSONL file records and parsed GroundTruthRecord lists.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime
from pathlib import Path

from backend.faults.models import FaultSpec, GroundTruthRecord

DEFAULT_GROUND_TRUTH_DIR = Path("data/raw/ground_truth")


class GroundTruthWriter:
    """Append-only writer for ground truth fault records."""

    def __init__(self, run_id: str, base_dir: Path | str | None = None) -> None:
        self.run_id = run_id
        self.base_dir = Path(base_dir) if base_dir is not None else DEFAULT_GROUND_TRUTH_DIR
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self.file_path = self.base_dir / f"{run_id}.jsonl"

    def record_fault(self, fault: FaultSpec, injected_at: datetime) -> GroundTruthRecord:
        """Append a fault injection event to the ground-truth JSONL log.

        Guaranteed append-only; never overwrites or truncates existing entries.
        """
        injected_utc = (
            injected_at.astimezone(UTC)
            if injected_at.tzinfo is not None
            else injected_at.replace(tzinfo=UTC)
        )
        record = GroundTruthRecord.from_fault(fault, injected_utc)

        # Open in append mode ("a") exclusively
        with open(self.file_path, "a", encoding="utf-8") as f:
            f.write(record.model_dump_json() + "\n")
            f.flush()
            os.fsync(f.fileno())

        return record


def read_ground_truth(
    run_id: str,
    base_dir: Path | str | None = None,
) -> list[GroundTruthRecord]:
    """Read and parse all ground-truth records for a given run ID."""
    dir_path = Path(base_dir) if base_dir is not None else DEFAULT_GROUND_TRUTH_DIR
    file_path = dir_path / f"{run_id}.jsonl"
    return read_ground_truth_file(file_path)


def read_ground_truth_file(file_path: Path | str) -> list[GroundTruthRecord]:
    """Read and parse all ground-truth records from a specific JSONL file path."""
    path = Path(file_path)
    if not path.exists():
        return []

    records: list[GroundTruthRecord] = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            stripped = line.strip()
            if stripped:
                records.append(GroundTruthRecord.model_validate_json(stripped))
    return records
