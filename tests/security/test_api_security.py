"""Security tests covering API robustness, input injection, rate limiting, and output redaction.

Purpose: Verifies Phase 6 acceptance tests:
         - SQL injection in device_id and sort fields returns 422 or an empty list, never a trace.
         - limit=100000 is clamped to 200.
         - A 1 MB body returns 413.
         - A forced exception returns generic JSON with a request ID and no traceback.
         - Security headers are present on every response.
         - The 61st request in a minute returns 429.
         - A fake key placed in a fake model response is redacted in the API response.
         - A second decision returns 409 and writes an audit event.
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime

import pytest
from backend.api.auth import create_api_key
from backend.api.main import create_app
from backend.limits.rate_limiter import get_rate_limiter
from backend.storage.database import get_session_factory, init_db
from backend.storage.models import (
    AlertRecord,
    AuditEventRecord,
    DiagnosisRecord,
    ProposalRecord,
)
from fastapi import APIRouter
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool


@pytest.fixture
def api_test_env() -> tuple[TestClient, Session, str, str, str]:
    """Provide initialized TestClient, DB session, viewer key, approver key, and proposal ID."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    init_db(engine)
    session_factory = get_session_factory(engine)
    session = session_factory()

    app = create_app(engine)

    # Route specifically to test forced unhandled exception (SEC-08)
    test_router = APIRouter(prefix="/v1")

    @test_router.get("/forced-error")
    def forced_error() -> None:
        raise RuntimeError("Secret internal failure detail that must not leak")

    app.include_router(test_router)

    client = TestClient(app, raise_server_exceptions=False)

    viewer_key, _ = create_api_key(session, label="sec-viewer", role="viewer")
    approver_key, _ = create_api_key(session, label="sec-approver", role="approver")

    # Insert test alert, diagnosis, and proposal
    alert_id = str(uuid.uuid4())
    diag_id = str(uuid.uuid4())
    prop_id = str(uuid.uuid4())

    alert = AlertRecord(
        alert_id=alert_id,
        device_id="INV-02",
        ts=datetime.now(UTC),
        rule="grid_sag",
        severity="warning",
        observed="195.0 V",
        threshold="207.0 V",
        message="Grid voltage sag detected",
    )
    session.add(alert)

    diag = DiagnosisRecord(
        diagnosis_id=diag_id,
        alert_id=alert_id,
        device_id="INV-02",
        cause="grid_sag",
        confidence=0.88,
        evidence_json="{}",
        prompt_version="v1",
        model="gemini-flash",
    )
    session.add(diag)

    prop = ProposalRecord(
        proposal_id=prop_id,
        diagnosis_id=diag_id,
        alert_id=alert_id,
        device_id="INV-02",
        action="disconnect_relay",
        justification="Disconnect relay. Internal key sk_live_secret1234567890abcdef12345 should be redacted.",
        status="pending",
    )
    session.add(prop)
    session.commit()

    # Reset rate limiter state for clean test run
    get_rate_limiter().reset()

    return client, session, viewer_key, approver_key, prop_id


def test_sql_injection_attempts_return_422_or_empty_list(
    api_test_env: tuple[TestClient, Session, str, str, str],
) -> None:
    client, _, viewer_key, _, _ = api_test_env
    headers = {"X-API-Key": viewer_key}

    # Injection in device_id
    resp = client.get("/v1/alerts?device_id=INV-01' OR '1'='1", headers=headers)
    assert resp.status_code in (422, 200)
    if resp.status_code == 200:
        assert resp.json()["items"] == []

    # Injection in sort_by
    resp2 = client.get("/v1/alerts?sort_by=ts; DROP TABLE alerts; --", headers=headers)
    assert resp2.status_code == 200
    # Parameterized query defaults to 'ts' if not in allowlist
    assert "error" not in resp2.text.lower() or resp2.status_code == 422


def test_limit_clamped_to_200(
    api_test_env: tuple[TestClient, Session, str, str, str],
) -> None:
    client, session, viewer_key, _, _ = api_test_env
    headers = {"X-API-Key": viewer_key}

    # Populate 250 alerts
    alerts = [
        AlertRecord(
            alert_id=str(uuid.uuid4()),
            device_id="INV-03",
            ts=datetime.now(UTC),
            rule="overheating",
            severity="critical",
            observed="62.0 C",
            threshold="60.0 C",
            message=f"Alert #{i}",
        )
        for i in range(250)
    ]
    session.add_all(alerts)
    session.commit()

    resp = client.get("/v1/alerts?limit=100000", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["items"]) <= 200
    assert data["count"] <= 200


def test_oversized_body_returns_413(
    api_test_env: tuple[TestClient, Session, str, str, str],
) -> None:
    client, _, _, approver_key, prop_id = api_test_env
    headers = {
        "X-API-Key": approver_key,
        "Content-Type": "application/json",
    }
    # 1 MB oversized payload (> 16 KB)
    huge_data = "x" * (1024 * 1024)
    payload = json.dumps({"decision": "approve", "reason": huge_data})

    resp = client.post(
        f"/v1/proposals/{prop_id}/decision",
        headers=headers,
        content=payload,
    )
    assert resp.status_code == 413
    assert "exceeds maximum limit" in resp.json()["detail"]


def test_forced_exception_returns_generic_json_with_request_id(
    api_test_env: tuple[TestClient, Session, str, str, str],
) -> None:
    client, _, _, _, _ = api_test_env
    resp = client.get("/v1/forced-error")
    assert resp.status_code == 500
    data = resp.json()
    assert data["error"] == "Internal server error"
    assert "request_id" in data
    assert resp.headers.get("X-Request-ID") == data["request_id"]
    # Verify no stack trace or internal error leaked
    assert "RuntimeError" not in resp.text
    assert "Secret internal failure detail" not in resp.text
    assert "Traceback" not in resp.text


def test_security_headers_present_on_all_responses(
    api_test_env: tuple[TestClient, Session, str, str, str],
) -> None:
    client, _, _, _, _ = api_test_env
    resp = client.get("/v1/health")
    assert resp.status_code == 200
    assert resp.headers.get("X-Content-Type-Options") == "nosniff"
    assert resp.headers.get("X-Frame-Options") == "DENY"
    assert "max-age=31536000" in resp.headers.get("Strict-Transport-Security", "")
    assert resp.headers.get("Content-Security-Policy") == "default-src 'self'"
    assert resp.headers.get("Referrer-Policy") == "no-referrer"
    assert "X-Request-ID" in resp.headers


def test_rate_limiter_blocks_61st_request(
    api_test_env: tuple[TestClient, Session, str, str, str],
) -> None:
    client, _, viewer_key, _, _ = api_test_env
    headers = {"X-API-Key": viewer_key}

    # Reset limiter
    get_rate_limiter().reset()

    # Send 60 requests in the window
    for _ in range(60):
        r = client.get("/v1/health", headers=headers)
        assert r.status_code == 200

    # 61st request must return HTTP 429
    r61 = client.get("/v1/health", headers=headers)
    assert r61.status_code == 429
    assert "Retry-After" in r61.headers
    assert int(r61.headers["Retry-After"]) >= 1


def test_fake_key_in_model_response_is_redacted(
    api_test_env: tuple[TestClient, Session, str, str, str],
) -> None:
    client, _, viewer_key, _, _ = api_test_env
    headers = {"X-API-Key": viewer_key}

    resp = client.get("/v1/proposals?status=pending", headers=headers)
    assert resp.status_code == 200
    # The proposal justification contained sk_live_secret...
    assert "[REDACTED:API_KEY]" in resp.text
    assert "sk_live_secret" not in resp.text


def test_second_decision_returns_409_and_writes_audit_event(
    api_test_env: tuple[TestClient, Session, str, str, str],
) -> None:
    client, session, _, approver_key, prop_id = api_test_env
    headers = {"X-API-Key": approver_key}

    # First decision -> 200 OK
    resp1 = client.post(
        f"/v1/proposals/{prop_id}/decision",
        headers=headers,
        json={"decision": "approve", "reason": "First valid decision"},
    )
    assert resp1.status_code == 200
    assert resp1.json()["status"] == "recorded"

    # Second decision -> 409 Conflict
    resp2 = client.post(
        f"/v1/proposals/{prop_id}/decision",
        headers=headers,
        json={"decision": "reject", "reason": "Second invalid decision"},
    )
    assert resp2.status_code == 409
    assert "already been decided" in resp2.json()["detail"]

    # Verify audit event was written to append-only log (SEC-70)
    audit_events = list(
        session.scalars(
            select(AuditEventRecord).where(
                AuditEventRecord.event_type == "duplicate_decision_rejected"
            )
        ).all()
    )
    assert len(audit_events) == 1
    event = audit_events[0]
    payload = json.loads(event.payload_json)
    assert payload["proposal_id"] == prop_id
    assert payload["attempted_decision"] == "reject"
