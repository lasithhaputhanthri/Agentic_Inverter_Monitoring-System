"""API route endpoints for solar inverter incident response system.

Purpose: Enforces SEC-06, SEC-07, SEC-20, SEC-21, SEC-22, SEC-23, and SEC-70.
Endpoints:
    - GET  /v1/health
    - GET  /v1/alerts
    - GET  /v1/alerts/{alert_id}
    - GET  /v1/fleet/status
    - GET  /v1/timeline
    - GET  /v1/proposals
    - POST /v1/proposals/{proposal_id}/decision
    - GET  /v1/usage
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from backend.api.deps import get_db, require_approver, require_viewer
from backend.api.schemas import (
    AlertListResponse,
    AlertResponse,
    DecisionRequest,
    DecisionResponse,
    FleetStatusResponse,
    HealthResponse,
    InverterStatusResponse,
    ProposalResponse,
    TimelineEventResponse,
    UsageResponse,
)
from backend.guard.input_validator import InputValidationError, scan_free_text
from backend.storage.models import ApiKeyRecord, ApprovalRecordItem
from backend.storage.repositories import (
    AlertRepository,
    AuditEventRepository,
    IncidentRepository,
    QuotaRepository,
    TelemetryRepository,
)

router = APIRouter(prefix="/v1")


@router.get("/health", response_model=HealthResponse)
def health_check() -> HealthResponse:
    """Unauthenticated health status check."""
    return HealthResponse(
        status="healthy",
        service="iir-backend",
        timestamp=datetime.now(UTC),
    )


@router.get("/auth/me")
def get_current_user_info(key: ApiKeyRecord = Depends(require_viewer)) -> dict[str, str]:
    """Return identity and access role for the authenticated API key."""
    return {"label": key.label, "role": key.role}


@router.get("/alerts", response_model=AlertListResponse)
def list_alerts(
    device_id: str | None = Query(default=None, pattern=r"^[A-Za-z0-9_-]{1,16}$"),
    rule: str | None = Query(default=None, max_length=64),
    severity: str | None = Query(default=None, max_length=32),
    cursor: str | None = Query(default=None, max_length=64),
    limit: int = Query(default=50, ge=1),
    sort_by: str = Query(default="ts"),
    sort_dir: str = Query(default="desc"),
    session: Session = Depends(get_db),
    _key: ApiKeyRecord = Depends(require_viewer),
) -> AlertListResponse:
    """List monitor alerts with parameterized filters, cursor pagination, and clamped limit."""
    clamped_limit = min(limit, 200)
    repo = AlertRepository(session)
    items, next_cursor = repo.list_alerts(
        device_id=device_id,
        rule=rule,
        severity=severity,
        cursor=cursor,
        limit=clamped_limit,
        sort_by=sort_by,
        sort_dir=sort_dir,
    )
    return AlertListResponse(
        items=[AlertResponse.model_validate(it) for it in items],
        next_cursor=next_cursor,
        count=len(items),
    )


@router.get("/alerts/{alert_id}", response_model=AlertResponse)
def get_alert(
    alert_id: str,
    session: Session = Depends(get_db),
    _key: ApiKeyRecord = Depends(require_viewer),
) -> AlertResponse:
    """Retrieve details of a single monitor alert."""
    repo = AlertRepository(session)
    record = repo.get_alert(alert_id)
    if not record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Alert '{alert_id}' not found",
        )
    return AlertResponse.model_validate(record)


@router.get("/fleet/status", response_model=FleetStatusResponse)
def get_fleet_status(
    session: Session = Depends(get_db),
    _key: ApiKeyRecord = Depends(require_viewer),
) -> FleetStatusResponse:
    """Fetch status snapshot across all 20 simulated inverters."""
    repo = TelemetryRepository(session)
    snapshot = repo.get_latest_fleet_snapshot()

    devices: list[InverterStatusResponse] = []
    total_active = 0

    for i in range(1, 21):
        dev_id = f"INV-{i:02d}"
        if dev_id in snapshot:
            s = snapshot[dev_id]
            is_active = s.status == "nominal" or s.status == "operational"
            if is_active:
                total_active += 1
            devices.append(
                InverterStatusResponse(
                    device_id=dev_id,
                    status=s.status,
                    ac_power_w=s.ac_power_w,
                    dc_voltage_v=s.dc_voltage_v,
                    grid_voltage_v=s.grid_voltage_v,
                    temperature_c=s.temperature_c,
                    relay_state=s.relay_state,
                    last_seen=s.ts,
                )
            )
        else:
            # Default nominal offline/idle standby representation
            devices.append(
                InverterStatusResponse(
                    device_id=dev_id,
                    status="nominal",
                    ac_power_w=0.0,
                    dc_voltage_v=0.0,
                    grid_voltage_v=230.0,
                    temperature_c=25.0,
                    relay_state="closed",
                    last_seen=None,
                )
            )

    return FleetStatusResponse(
        devices=devices,
        total_active=total_active,
        total_devices=20,
    )


@router.get("/timeline", response_model=list[TimelineEventResponse])
def get_timeline(
    run_id: str | None = Query(default=None, max_length=64),
    session: Session = Depends(get_db),
    _key: ApiKeyRecord = Depends(require_viewer),
) -> list[TimelineEventResponse]:
    """Retrieve unified chronological incident lifecycle events."""
    repo = IncidentRepository(session)
    events = repo.get_timeline(run_id=run_id)
    return [TimelineEventResponse.model_validate(e) for e in events]


@router.get("/proposals", response_model=list[ProposalResponse])
def list_proposals(
    proposal_status: str | None = Query(default="pending", alias="status", max_length=32),
    limit: int = Query(default=50, ge=1),
    session: Session = Depends(get_db),
    _key: ApiKeyRecord = Depends(require_viewer),
) -> list[ProposalResponse]:
    """List remediation proposals by status."""
    clamped_limit = min(limit, 200)
    repo = IncidentRepository(session)
    items = repo.list_proposals(status=proposal_status, limit=clamped_limit)
    return [ProposalResponse.model_validate(p) for p in items]


@router.post("/proposals/{proposal_id}/decision", response_model=DecisionResponse)
def submit_decision(
    proposal_id: str,
    body: DecisionRequest,
    session: Session = Depends(get_db),
    key: ApiKeyRecord = Depends(require_approver),
) -> DecisionResponse:
    """Submit human approval or rejection for a remediation proposal."""
    incident_repo = IncidentRepository(session)
    audit_repo = AuditEventRepository(session)

    proposal = incident_repo.get_proposal(proposal_id)
    if not proposal:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Proposal '{proposal_id}' not found",
        )

    # Check for once-only decision (SEC-22, SEC-23)
    existing_approval = incident_repo.get_approval(proposal_id)
    if existing_approval:
        # Record duplicate decision attempt in append-only audit log
        audit_repo.append(
            event_id=str(uuid.uuid4()),
            event_type="duplicate_decision_rejected",
            payload={
                "proposal_id": proposal_id,
                "approver_id": key.label,
                "attempted_decision": body.decision,
            },
        )
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Proposal '{proposal_id}' has already been decided",
        )

    # Process and sanitize operator reason text if provided (Rule 50)
    cleaned_reason: str | None = None
    if body.reason:
        try:
            validated = scan_free_text(body.reason)
            if validated.is_injection_flagged:
                audit_repo.append(
                    event_id=str(uuid.uuid4()),
                    event_type="injection_flagged_decision_attempt",
                    payload={"proposal_id": proposal_id, "approver_id": key.label},
                )
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail="Decision rejected: suspicious text pattern detected",
                )
            cleaned_reason = validated.sanitized_text
        except InputValidationError as e:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=str(e),
            ) from e

    approval_id = str(uuid.uuid4())
    record = ApprovalRecordItem(
        approval_id=approval_id,
        proposal_id=proposal_id,
        approver_id=key.label,
        decision=body.decision,
        reason=cleaned_reason,
        created_at=datetime.now(UTC),
    )
    incident_repo.record_approval(record)

    # Record successful approval in append-only audit log
    audit_repo.append(
        event_id=str(uuid.uuid4()),
        event_type="proposal_decision_recorded",
        payload={
            "approval_id": approval_id,
            "proposal_id": proposal_id,
            "approver_id": key.label,
            "decision": body.decision,
        },
    )

    return DecisionResponse(
        status="recorded",
        proposal_id=proposal_id,
        approval_id=approval_id,
        decision=body.decision,
    )


@router.get("/usage", response_model=UsageResponse)
def get_quota_usage(
    session: Session = Depends(get_db),
    _key: ApiKeyRecord = Depends(require_viewer),
) -> UsageResponse:
    """Retrieve current daily quota and consumption metrics."""
    today = datetime.now(UTC).strftime("%Y-%m-%d")
    repo = QuotaRepository(session)
    usage = repo.get_usage(today)

    return UsageResponse(
        usage_date=today,
        request_count=usage.request_count if usage else 0,
        llm_call_count=usage.llm_call_count if usage else 0,
        tokens_used=usage.tokens_used if usage else 0,
    )
