"""Unit tests for storage repositories layer.

Purpose: Verifies SEC-07 (parameterized queries, allowlists), SEC-62 (7-day telemetry retention),
         and SEC-70 (append-only audit trail).
"""

from __future__ import annotations

import uuid
from collections.abc import Generator
from datetime import UTC, datetime, timedelta

import pytest
from backend.storage.database import get_session_factory, init_db
from backend.storage.models import (
    AlertRecord,
    ApprovalRecordItem,
    DiagnosisRecord,
    ExecutionRecordItem,
    ProposalRecord,
    TelemetryRecord,
)
from backend.storage.repositories import (
    AlertRepository,
    AuditEventRepository,
    IncidentRepository,
    RunRepository,
    TelemetryRepository,
)
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool


@pytest.fixture
def db_session() -> Generator[Session, None, None]:
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    init_db(engine)
    session_factory = get_session_factory(engine)
    session = session_factory()
    yield session
    session.close()


def test_run_repository(db_session: Session) -> None:
    repo = RunRepository(db_session)
    now = datetime.now(UTC)
    run = repo.create_run("run-001", seed=42, duration_s=60.0, started_at=now)
    assert run.run_id == "run-001"
    assert run.status == "running"

    fetched = repo.get_run("run-001")
    assert fetched is not None
    assert fetched.seed == 42

    repo.finish_run("run-001", completed_at=now + timedelta(seconds=60), status="completed")
    updated = repo.get_run("run-001")
    assert updated is not None
    assert updated.status == "completed"


def test_telemetry_repository_retention(db_session: Session) -> None:
    repo = TelemetryRepository(db_session)
    now = datetime.now(UTC)

    # 1. Recent sample (1 hour ago)
    recent = TelemetryRecord(
        device_id="INV-01",
        ts=now - timedelta(hours=1),
        ac_power_w=3000.0,
        dc_voltage_v=400.0,
        grid_voltage_v=230.0,
        temperature_c=45.0,
        relay_state="closed",
        status="nominal",
    )
    # 2. Old sample (8 days ago)
    old = TelemetryRecord(
        device_id="INV-01",
        ts=now - timedelta(days=8),
        ac_power_w=2800.0,
        dc_voltage_v=395.0,
        grid_voltage_v=229.0,
        temperature_c=42.0,
        relay_state="closed",
        status="nominal",
    )
    repo.add_samples([recent, old])

    # Enforce SEC-62 retention cleanup (7 days)
    deleted_count = repo.cleanup_older_than(days=7, ref_time=now)
    assert deleted_count == 1

    # Only recent remains
    remaining = repo.get_recent("INV-01", minutes=120, ref_time=now)
    assert len(remaining) == 1
    assert remaining[0].ts == recent.ts


def test_alert_repository_allowlist_and_pagination(db_session: Session) -> None:
    repo = AlertRepository(db_session)
    now = datetime.now(UTC)

    for i in range(10):
        repo.create_alert(
            AlertRecord(
                alert_id=f"alt-{i:02d}",
                device_id=f"INV-{(i % 3) + 1:02d}",
                ts=now - timedelta(minutes=i),
                rule="overheating",
                severity="critical" if i % 2 == 0 else "warning",
                observed="65 C",
                threshold="60 C",
                message=f"Alert {i}",
            )
        )

    # Test filtering and sorting
    alerts, _ = repo.list_alerts(device_id="INV-01", sort_by="ts", sort_dir="desc")
    assert len(alerts) > 0
    for a in alerts:
        assert a.device_id == "INV-01"

    # Test invalid sort field falls back safely to 'ts' (SEC-07)
    safe_alerts, _ = repo.list_alerts(sort_by="invalid_col_name", sort_dir="unknown_dir")
    assert len(safe_alerts) == 10


def test_audit_event_repository_is_append_only(db_session: Session) -> None:
    repo = AuditEventRepository(db_session)
    evt_id = str(uuid.uuid4())
    rec = repo.append(evt_id, "test_event", {"key": "val"})
    assert rec.event_id == evt_id

    events = repo.list_events()
    assert len(events) == 1
    assert events[0].event_type == "test_event"

    # Verify no update or delete methods exist on repository (SEC-70)
    assert not hasattr(repo, "update")
    assert not hasattr(repo, "delete")
    assert not hasattr(repo, "remove")


def test_incident_repository_lifecycle_and_timeline(db_session: Session) -> None:
    repo = IncidentRepository(db_session)

    diag_id = str(uuid.uuid4())
    prop_id = str(uuid.uuid4())
    app_id = str(uuid.uuid4())
    exec_id = str(uuid.uuid4())

    repo.create_diagnosis(
        DiagnosisRecord(
            diagnosis_id=diag_id,
            alert_id="alt-01",
            device_id="INV-01",
            cause="overheating",
            confidence=0.9,
            evidence_json="{}",
            prompt_version="v1",
            model="gemini",
        )
    )

    repo.create_proposal(
        ProposalRecord(
            proposal_id=prop_id,
            diagnosis_id=diag_id,
            alert_id="alt-01",
            device_id="INV-01",
            action="curtail_50",
            justification="Curtail output by 50%",
            status="pending",
        )
    )

    repo.record_approval(
        ApprovalRecordItem(
            approval_id=app_id,
            proposal_id=prop_id,
            approver_id="operator_bob",
            decision="approve",
            reason="Thermal limit approaching",
        )
    )

    repo.record_execution(
        ExecutionRecordItem(
            execution_id=exec_id,
            proposal_id=prop_id,
            device_id="INV-01",
            action="curtail_50",
            status="executed",
            details_json="{}",
        )
    )

    timeline = repo.get_timeline()
    assert len(timeline) >= 4
    types = [t["type"] for t in timeline]
    assert "diagnosis" in types
    assert "proposal" in types
    assert "approval" in types
    assert "execution" in types
