"""Script to generate a sample incident timeline for Phase 6 report."""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

from backend.storage.database import get_session_factory, init_db
from backend.storage.models import (
    AlertRecord,
    ApprovalRecordItem,
    DiagnosisRecord,
    ExecutionRecordItem,
    ProposalRecord,
)
from backend.storage.repositories import IncidentRepository
from sqlalchemy import create_engine


def main() -> None:
    engine = create_engine("sqlite:///:memory:")
    init_db(engine)
    session = get_session_factory(engine)()
    repo = IncidentRepository(session)
    now = datetime(2026, 11, 9, 10, 0, 0, tzinfo=UTC)

    alt_id = str(uuid.uuid4())
    diag_id = str(uuid.uuid4())
    prop_id = str(uuid.uuid4())
    app_id = str(uuid.uuid4())
    exec_id = str(uuid.uuid4())

    session.add(
        AlertRecord(
            alert_id=alt_id,
            device_id="INV-05",
            ts=now,
            rule="temp_high_for_power",
            severity="critical",
            observed="68.5 C",
            threshold="60.0 C",
            message="Critical inverter core temperature exceeded",
        )
    )
    repo.create_diagnosis(
        DiagnosisRecord(
            diagnosis_id=diag_id,
            alert_id=alt_id,
            device_id="INV-05",
            cause="overheating",
            confidence=0.96,
            evidence_json="{}",
            prompt_version="v1.0",
            model="gemini-flash",
            created_at=now + timedelta(seconds=10),
        )
    )
    repo.create_proposal(
        ProposalRecord(
            proposal_id=prop_id,
            diagnosis_id=diag_id,
            alert_id=alt_id,
            device_id="INV-05",
            action="curtail_50",
            justification="Inverter overheating; curtailing active output power by 50% to prevent thermal shutdown",
            status="pending",
            created_at=now + timedelta(seconds=20),
        )
    )
    repo.record_approval(
        ApprovalRecordItem(
            approval_id=app_id,
            proposal_id=prop_id,
            approver_id="operator_jane",
            decision="approve",
            reason="Thermal risk confirmed. Curtailment approved.",
            created_at=now + timedelta(seconds=60),
        )
    )
    repo.record_execution(
        ExecutionRecordItem(
            execution_id=exec_id,
            proposal_id=prop_id,
            device_id="INV-05",
            action="curtail_50",
            status="executed",
            details_json=json.dumps({"curtailment_percent": 50}),
            created_at=now + timedelta(seconds=70),
        )
    )

    timeline = repo.get_timeline()
    out_lines = [
        "# Incident Response Workflow Phase 6 Timeline Dump",
        f"# Device: INV-05 | Alert ID: {alt_id}",
        "# ----------------------------------------------------------------------",
    ]
    for ev in timeline:
        out_lines.append(f"[{ev['timestamp']}] [{ev['type'].upper()}] {ev['summary']}")

    out_text = "\n".join(out_lines) + "\n"
    out_path = Path("docs/demo/phase6_timeline.txt")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(out_text, encoding="utf-8")
    print(out_text)


if __name__ == "__main__":
    main()
