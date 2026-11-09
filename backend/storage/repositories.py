"""Repository layer for parameterized, type-safe database access.

Purpose: Enforces SEC-07 (parameterized queries, filter/sort allowlists), SEC-62 (7-day telemetry retention),
         and SEC-70 (append-only audit trail) across all data aggregates.
Inputs: SQLAlchemy Sessions, strongly-typed filter arguments, and data models.
Outputs: Domain aggregate records and paginated query results.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from backend.storage.models import (
    AlertRecord,
    ApiKeyRecord,
    ApprovalRecordItem,
    AuditEventRecord,
    DiagnosisRecord,
    ExecutionRecordItem,
    LLMCallRecord,
    ProposalRecord,
    QuotaUsageRecord,
    RunRecord,
    TelemetryRecord,
)

ALERT_SORT_ALLOWLIST = {"ts", "created_at", "device_id", "severity"}
SORT_DIR_ALLOWLIST = {"asc", "desc"}
DEFAULT_LIST_LIMIT = 50
MAX_LIST_LIMIT = 200


class RunRepository:
    """Repository for execution and simulation runs."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def create_run(
        self,
        run_id: str,
        seed: int,
        duration_s: float,
        started_at: datetime,
        status: str = "running",
    ) -> RunRecord:
        record = RunRecord(
            run_id=run_id,
            seed=seed,
            duration_s=duration_s,
            started_at=started_at,
            status=status,
        )
        self.session.add(record)
        self.session.commit()
        return record

    def get_run(self, run_id: str) -> RunRecord | None:
        stmt = select(RunRecord).where(RunRecord.run_id == run_id)
        return self.session.scalars(stmt).first()

    def finish_run(self, run_id: str, completed_at: datetime, status: str = "completed") -> None:
        record = self.get_run(run_id)
        if record:
            record.completed_at = completed_at
            record.status = status
            self.session.commit()


class TelemetryRepository:
    """Repository for physical inverter telemetry metrics and retention cleanup."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def add_sample(self, record: TelemetryRecord) -> None:
        self.session.add(record)
        self.session.commit()

    def add_samples(self, records: list[TelemetryRecord]) -> None:
        self.session.add_all(records)
        self.session.commit()

    def get_recent(
        self, device_id: str, minutes: int = 15, ref_time: datetime | None = None
    ) -> list[TelemetryRecord]:
        now = ref_time or datetime.now(UTC)
        cutoff = now - timedelta(minutes=minutes)
        stmt = (
            select(TelemetryRecord)
            .where(TelemetryRecord.device_id == device_id, TelemetryRecord.ts >= cutoff)
            .order_by(TelemetryRecord.ts.asc())
            .limit(60)
        )
        return list(self.session.scalars(stmt).all())

    def get_latest_fleet_snapshot(self) -> dict[str, TelemetryRecord]:
        """Fetch the most recent telemetry sample for each device in the fleet."""
        subquery = (
            select(
                TelemetryRecord.device_id,
                func.max(TelemetryRecord.ts).label("max_ts"),
            )
            .group_by(TelemetryRecord.device_id)
            .subquery()
        )

        stmt = select(TelemetryRecord).join(
            subquery,
            (TelemetryRecord.device_id == subquery.c.device_id)
            & (TelemetryRecord.ts == subquery.c.max_ts),
        )
        samples = self.session.scalars(stmt).all()
        return {s.device_id: s for s in samples}

    def cleanup_older_than(self, days: int = 7, ref_time: datetime | None = None) -> int:
        """Enforce SEC-62 retention policy: delete raw telemetry older than configured days."""
        now = ref_time or datetime.now(UTC)
        cutoff = now - timedelta(days=days)
        stmt = select(TelemetryRecord).where(TelemetryRecord.ts < cutoff)
        old_records = list(self.session.scalars(stmt).all())
        count = len(old_records)
        for r in old_records:
            self.session.delete(r)
        self.session.commit()
        return count


class AlertRepository:
    """Repository for monitor alerts with parameterized filters and cursor pagination."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def create_alert(self, record: AlertRecord) -> AlertRecord:
        self.session.add(record)
        self.session.commit()
        return record

    def get_alert(self, alert_id: str) -> AlertRecord | None:
        stmt = select(AlertRecord).where(AlertRecord.alert_id == alert_id)
        return self.session.scalars(stmt).first()

    def list_alerts(
        self,
        device_id: str | None = None,
        rule: str | None = None,
        severity: str | None = None,
        cursor: str | None = None,
        limit: int = DEFAULT_LIST_LIMIT,
        sort_by: str = "ts",
        sort_dir: str = "desc",
    ) -> tuple[list[AlertRecord], str | None]:
        """List alerts with strict sort/filter allowlisting and limit clamping (SEC-07)."""
        clamped_limit = min(max(1, limit), MAX_LIST_LIMIT)

        # Allowlist validation to prevent SQL injection (SEC-07)
        if sort_by not in ALERT_SORT_ALLOWLIST:
            sort_by = "ts"
        if sort_dir.lower() not in SORT_DIR_ALLOWLIST:
            sort_dir = "desc"

        col = getattr(AlertRecord, sort_by)
        order_expr = desc(col) if sort_dir.lower() == "desc" else col

        stmt = select(AlertRecord)
        if device_id:
            stmt = stmt.where(AlertRecord.device_id == device_id)
        if rule:
            stmt = stmt.where(AlertRecord.rule == rule)
        if severity:
            stmt = stmt.where(AlertRecord.severity == severity)
        if cursor:
            # Simple timestamp cursor
            try:
                cursor_dt = datetime.fromisoformat(cursor)
                if sort_dir.lower() == "desc":
                    stmt = stmt.where(AlertRecord.ts < cursor_dt)
                else:
                    stmt = stmt.where(AlertRecord.ts > cursor_dt)
            except ValueError:
                pass

        stmt = stmt.order_by(order_expr).limit(clamped_limit + 1)
        results = list(self.session.scalars(stmt).all())

        next_cursor: str | None = None
        if len(results) > clamped_limit:
            results = results[:clamped_limit]
            next_cursor = results[-1].ts.isoformat()

        return results, next_cursor


class IncidentRepository:
    """Repository for diagnoses, proposals, approvals, and executions."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def create_diagnosis(self, record: DiagnosisRecord) -> DiagnosisRecord:
        self.session.add(record)
        self.session.commit()
        return record

    def get_diagnosis_for_alert(self, alert_id: str) -> DiagnosisRecord | None:
        stmt = select(DiagnosisRecord).where(DiagnosisRecord.alert_id == alert_id)
        return self.session.scalars(stmt).first()

    def create_proposal(self, record: ProposalRecord) -> ProposalRecord:
        self.session.add(record)
        self.session.commit()
        return record

    def get_proposal(self, proposal_id: str) -> ProposalRecord | None:
        stmt = select(ProposalRecord).where(ProposalRecord.proposal_id == proposal_id)
        return self.session.scalars(stmt).first()

    def list_proposals(
        self, status: str | None = None, limit: int = DEFAULT_LIST_LIMIT
    ) -> list[ProposalRecord]:
        clamped_limit = min(max(1, limit), MAX_LIST_LIMIT)
        stmt = select(ProposalRecord)
        if status:
            stmt = stmt.where(ProposalRecord.status == status)
        stmt = stmt.order_by(ProposalRecord.created_at.desc()).limit(clamped_limit)
        return list(self.session.scalars(stmt).all())

    def record_approval(self, record: ApprovalRecordItem) -> ApprovalRecordItem:
        self.session.add(record)
        # Also update proposal status
        prop = self.get_proposal(record.proposal_id)
        if prop:
            prop.status = "approved" if record.decision.lower() == "approve" else "rejected"
        self.session.commit()
        return record

    def get_approval(self, proposal_id: str) -> ApprovalRecordItem | None:
        stmt = select(ApprovalRecordItem).where(ApprovalRecordItem.proposal_id == proposal_id)
        return self.session.scalars(stmt).first()

    def record_execution(self, record: ExecutionRecordItem) -> ExecutionRecordItem:
        self.session.add(record)
        prop = self.get_proposal(record.proposal_id)
        if prop:
            prop.status = "executed" if record.status == "executed" else "execution_refused"
        self.session.commit()
        return record

    def get_execution(self, proposal_id: str) -> ExecutionRecordItem | None:
        stmt = select(ExecutionRecordItem).where(ExecutionRecordItem.proposal_id == proposal_id)
        return self.session.scalars(stmt).first()

    def get_timeline(self, run_id: str | None = None) -> list[dict[str, Any]]:
        """Construct unified chronological timeline of all incident response lifecycle events."""
        events: list[dict[str, Any]] = []

        # 1. Alerts
        alert_stmt = select(AlertRecord)
        if run_id:
            alert_stmt = alert_stmt.where(AlertRecord.run_id == run_id)
        for a in self.session.scalars(alert_stmt).all():
            events.append(
                {
                    "type": "alert",
                    "id": a.alert_id,
                    "device_id": a.device_id,
                    "timestamp": a.ts.isoformat(),
                    "summary": f"Alert {a.rule} ({a.severity}): observed {a.observed}",
                }
            )

        # 2. Diagnoses
        diag_stmt = select(DiagnosisRecord)
        for d in self.session.scalars(diag_stmt).all():
            events.append(
                {
                    "type": "diagnosis",
                    "id": d.diagnosis_id,
                    "device_id": d.device_id,
                    "timestamp": d.created_at.isoformat(),
                    "summary": f"Diagnosed cause '{d.cause}' with {d.confidence:.0%} confidence",
                }
            )

        # 3. Proposals
        prop_stmt = select(ProposalRecord)
        for p in self.session.scalars(prop_stmt).all():
            events.append(
                {
                    "type": "proposal",
                    "id": p.proposal_id,
                    "device_id": p.device_id,
                    "timestamp": p.created_at.isoformat(),
                    "summary": f"Proposed action '{p.action}': {p.justification[:60]}",
                }
            )

        # 4. Approvals
        app_stmt = select(ApprovalRecordItem)
        for ap in self.session.scalars(app_stmt).all():
            events.append(
                {
                    "type": "approval",
                    "id": ap.approval_id,
                    "proposal_id": ap.proposal_id,
                    "timestamp": ap.created_at.isoformat(),
                    "summary": f"Operator '{ap.approver_id}' {ap.decision.upper()}: {ap.reason or 'No note'}",
                }
            )

        # 5. Executions
        exec_stmt = select(ExecutionRecordItem)
        for ex in self.session.scalars(exec_stmt).all():
            events.append(
                {
                    "type": "execution",
                    "id": ex.execution_id,
                    "device_id": ex.device_id,
                    "timestamp": ex.created_at.isoformat(),
                    "summary": f"Action '{ex.action}' status '{ex.status}'",
                }
            )

        # Sort chronologically
        events.sort(key=lambda x: x["timestamp"])
        return events


class AuditEventRepository:
    """Strictly append-only repository for audit events. Has no update or delete methods (SEC-70)."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def append(
        self,
        event_id: str,
        event_type: str,
        payload: dict[str, Any],
        timestamp: datetime | None = None,
    ) -> AuditEventRecord:
        record = AuditEventRecord(
            event_id=event_id,
            event_type=event_type,
            payload_json=json.dumps(payload),
            created_at=timestamp or datetime.now(UTC),
        )
        self.session.add(record)
        self.session.commit()
        return record

    def list_events(self, limit: int = 200) -> list[AuditEventRecord]:
        stmt = (
            select(AuditEventRecord)
            .order_by(AuditEventRecord.created_at.desc())
            .limit(min(limit, MAX_LIST_LIMIT))
        )
        return list(self.session.scalars(stmt).all())


class ApiKeyRepository:
    """Repository for API credentials."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def create_key(
        self,
        label: str,
        role: str,
        key_hash: str,
        key_prefix: str,
        salt: str,
    ) -> ApiKeyRecord:
        record = ApiKeyRecord(
            label=label,
            role=role,
            key_hash=key_hash,
            key_prefix=key_prefix,
            salt=salt,
        )
        self.session.add(record)
        self.session.commit()
        return record

    def get_by_prefix(self, prefix: str) -> list[ApiKeyRecord]:
        stmt = select(ApiKeyRecord).where(ApiKeyRecord.key_prefix == prefix)
        return list(self.session.scalars(stmt).all())

    def revoke_key(self, key_id: int) -> bool:
        stmt = select(ApiKeyRecord).where(ApiKeyRecord.id == key_id)
        record = self.session.scalars(stmt).first()
        if record:
            record.revoked_at = datetime.now(UTC)
            self.session.commit()
            return True
        return False


class QuotaRepository:
    """Repository for API rate limiting and token usage quotas."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def record_request(self, date_str: str) -> int:
        stmt = select(QuotaUsageRecord).where(QuotaUsageRecord.usage_date == date_str)
        record = self.session.scalars(stmt).first()
        if not record:
            record = QuotaUsageRecord(usage_date=date_str, request_count=1)
            self.session.add(record)
        else:
            record.request_count += 1
        self.session.commit()
        return record.request_count

    def record_llm_call(self, record: LLMCallRecord) -> None:
        self.session.add(record)
        today = record.created_at.strftime("%Y-%m-%d")
        stmt = select(QuotaUsageRecord).where(QuotaUsageRecord.usage_date == today)
        quota_rec = self.session.scalars(stmt).first()
        if not quota_rec:
            quota_rec = QuotaUsageRecord(
                usage_date=today,
                llm_call_count=1,
                tokens_used=record.input_tokens + record.output_tokens,
            )
            self.session.add(quota_rec)
        else:
            quota_rec.llm_call_count += 1
            quota_rec.tokens_used += record.input_tokens + record.output_tokens
        self.session.commit()

    def get_usage(self, date_str: str) -> QuotaUsageRecord | None:
        stmt = select(QuotaUsageRecord).where(QuotaUsageRecord.usage_date == date_str)
        return self.session.scalars(stmt).first()
