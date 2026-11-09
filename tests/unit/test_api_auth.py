"""Unit tests for API authentication and role authorization.

Purpose: Verifies Phase 6 acceptance tests:
         - Missing key returns 401.
         - Wrong key returns 401.
         - Revoked key returns 401.
         - A viewer on the approve route returns 403.
         - An approver returns 200.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from backend.api.auth import create_api_key
from backend.api.main import create_app
from backend.storage.database import get_session_factory, init_db
from backend.storage.models import AlertRecord, DiagnosisRecord, ProposalRecord
from backend.storage.repositories import ApiKeyRepository
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool


@pytest.fixture
def test_setup() -> tuple[TestClient, Session, str, str, str, str]:
    """Setup in-memory SQLite DB, app test client, viewer key, approver key, and test proposal."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    init_db(engine)
    session_factory = get_session_factory(engine)
    session = session_factory()

    app = create_app(engine)
    client = TestClient(app)

    # Create viewer key
    viewer_key, _ = create_api_key(session, label="test-viewer", role="viewer")

    # Create approver key
    approver_key, _ = create_api_key(session, label="test-approver", role="approver")

    # Create revoked key
    revoked_key, revoked_rec = create_api_key(session, label="test-revoked", role="approver")
    api_repo = ApiKeyRepository(session)
    api_repo.revoke_key(revoked_rec.id)

    # Insert a dummy alert, diagnosis, and proposal to test approval route
    alert_id = str(uuid.uuid4())
    diag_id = str(uuid.uuid4())
    prop_id = str(uuid.uuid4())

    alert = AlertRecord(
        alert_id=alert_id,
        device_id="INV-01",
        ts=datetime.now(UTC),
        rule="overheating",
        severity="critical",
        observed="65.0 C",
        threshold="60.0 C",
        message="Inverter overheating detected",
    )
    session.add(alert)

    diag = DiagnosisRecord(
        diagnosis_id=diag_id,
        alert_id=alert_id,
        device_id="INV-01",
        cause="overheating",
        confidence=0.95,
        evidence_json="{}",
        prompt_version="v1",
        model="dummy-model",
    )
    session.add(diag)

    prop = ProposalRecord(
        proposal_id=prop_id,
        diagnosis_id=diag_id,
        alert_id=alert_id,
        device_id="INV-01",
        action="curtail_50",
        justification="Curtail output by 50% to prevent thermal runaway",
        status="pending",
    )
    session.add(prop)
    session.commit()

    return client, session, viewer_key, approver_key, revoked_key, prop_id


def test_missing_key_returns_401(
    test_setup: tuple[TestClient, Session, str, str, str, str],
) -> None:
    client, _, _, _, _, _ = test_setup
    resp = client.get("/v1/alerts")
    assert resp.status_code == 401
    assert "Missing required X-API-Key" in resp.json()["detail"]


def test_wrong_key_returns_401(test_setup: tuple[TestClient, Session, str, str, str, str]) -> None:
    client, _, _, _, _, _ = test_setup
    resp = client.get("/v1/alerts", headers={"X-API-Key": "completely_invalid_key_12345"})
    assert resp.status_code == 401
    assert "Invalid or revoked API key" in resp.json()["detail"]


def test_revoked_key_returns_401(
    test_setup: tuple[TestClient, Session, str, str, str, str],
) -> None:
    client, _, _, _, revoked_key, _ = test_setup
    resp = client.get("/v1/alerts", headers={"X-API-Key": revoked_key})
    assert resp.status_code == 401
    assert "Invalid or revoked API key" in resp.json()["detail"]


def test_viewer_on_approve_route_returns_403(
    test_setup: tuple[TestClient, Session, str, str, str, str],
) -> None:
    client, _, viewer_key, _, _, prop_id = test_setup
    resp = client.post(
        f"/v1/proposals/{prop_id}/decision",
        headers={"X-API-Key": viewer_key},
        json={"decision": "approve", "reason": "Operator approved"},
    )
    assert resp.status_code == 403
    assert "approver role required" in resp.json()["detail"]


def test_approver_on_approve_route_returns_200(
    test_setup: tuple[TestClient, Session, str, str, str, str],
) -> None:
    client, _, _, approver_key, _, prop_id = test_setup
    resp = client.post(
        f"/v1/proposals/{prop_id}/decision",
        headers={"X-API-Key": approver_key},
        json={"decision": "approve", "reason": "Operator approved"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "recorded"
    assert data["proposal_id"] == prop_id
    assert data["decision"] == "approve"
    assert "approval_id" in data
