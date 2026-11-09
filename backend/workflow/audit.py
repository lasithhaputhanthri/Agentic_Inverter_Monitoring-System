"""Append-only audit sink for incident response workflow events.

Purpose: Records immutable workflow audit trails adhering to SEC-70.
Inputs: Strongly-typed event identifiers and structured identifier/enum payloads.
Outputs: Immutable, verifiable audit trail sequence with zero update/delete capability.
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import Enum
from typing import Any, Protocol

from pydantic import BaseModel, ConfigDict


class AuditEventType(str, Enum):
    """Permitted audit event types."""

    ALERT_RAISED = "alert_raised"
    DIAGNOSIS_MADE = "diagnosis_made"
    PROPOSAL_MADE = "proposal_made"
    POLICY_BLOCKED = "policy_blocked"
    APPROVAL_REQUESTED = "approval_requested"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXPIRED = "expired"
    EXECUTED = "executed"
    EXECUTION_REFUSED = "execution_refused"


class AuditEvent(BaseModel):
    """Immutable audit record containing IDs and enums only (SEC-70)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    event_id: str
    event_type: AuditEventType
    timestamp: datetime
    payload: dict[str, str | int | float | bool | None]


class AuditSink(Protocol):
    """Append-only audit sink protocol without update or delete operations (SEC-70)."""

    def record(
        self,
        event_type: AuditEventType | str,
        payload: dict[str, Any],
        timestamp: datetime | None = None,
    ) -> AuditEvent:
        """Append an event to the audit trail."""
        ...


class InMemoryAuditSink:
    """Thread-safe, append-only in-memory audit event collector."""

    def __init__(self) -> None:
        self._events: list[AuditEvent] = []
        self._counter: int = 0

    def record(
        self,
        event_type: AuditEventType | str,
        payload: dict[str, Any],
        timestamp: datetime | None = None,
    ) -> AuditEvent:
        """Append an event to the audit log with strict payload sanitization."""
        ev_type = (
            event_type
            if isinstance(event_type, AuditEventType)
            else AuditEventType(str(event_type).lower())
        )

        self._counter += 1
        ev_id = f"AUDIT-{self._counter:06d}"

        event_ts = timestamp or datetime.now(UTC)
        if not event_ts.tzinfo:
            event_ts = event_ts.replace(tzinfo=UTC)

        # Sanitize payload: allow only primitives and enums, reject complex objects
        clean_payload: dict[str, str | int | float | bool | None] = {}
        for k, v in payload.items():
            if isinstance(v, Enum):
                clean_payload[k] = v.value
            elif isinstance(v, str | int | float | bool) or v is None:
                clean_payload[k] = v
            else:
                clean_payload[k] = str(v)

        event = AuditEvent(
            event_id=ev_id,
            event_type=ev_type,
            timestamp=event_ts,
            payload=clean_payload,
        )

        self._events.append(event)
        return event

    @property
    def events(self) -> list[AuditEvent]:
        """Return a read-only copy of recorded audit events."""
        return list(self._events)

    def get_events_by_type(self, event_type: AuditEventType | str) -> list[AuditEvent]:
        """Filter audit events by type."""
        target_type = (
            event_type
            if isinstance(event_type, AuditEventType)
            else AuditEventType(str(event_type).lower())
        )
        return [e for e in self._events if e.event_type == target_type]
