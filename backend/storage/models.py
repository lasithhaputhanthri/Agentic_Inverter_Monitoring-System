"""SQLAlchemy 2.x declarative models for the IIR persistent storage layer.

Purpose: Defines relational tables for fleet runs, telemetry, alerts, incidents,
         approvals, executions, append-only audit events, API keys, and quota tracking.
Inputs: Strongly-typed SQLAlchemy Mapped columns and relationships.
Outputs: SQLAlchemy declarative Base and model classes.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import (
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    """Base declarative class for all SQLAlchemy ORM models."""

    pass


class RunRecord(Base):
    """Execution run metadata for simulation batches or continuous monitoring sessions."""

    __tablename__ = "runs"

    run_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    seed: Mapped[int] = mapped_column(Integer, nullable=False)
    duration_s: Mapped[float] = mapped_column(Float, nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="running", nullable=False)

    # Relationships
    telemetry: Mapped[list[TelemetryRecord]] = relationship(
        back_populates="run", cascade="all, delete-orphan"
    )
    alerts: Mapped[list[AlertRecord]] = relationship(back_populates="run")


class TelemetryRecord(Base):
    """Sampled physical inverter telemetry metrics with retention tracking."""

    __tablename__ = "telemetry_samples"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("runs.run_id", ondelete="CASCADE"), nullable=True, index=True
    )
    device_id: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    ac_power_w: Mapped[float] = mapped_column(Float, nullable=False)
    dc_voltage_v: Mapped[float] = mapped_column(Float, nullable=False)
    grid_voltage_v: Mapped[float] = mapped_column(Float, nullable=False)
    temperature_c: Mapped[float] = mapped_column(Float, nullable=False)
    relay_state: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )

    run: Mapped[RunRecord | None] = relationship(back_populates="telemetry")

    __table_args__ = (Index("ix_telemetry_device_ts", "device_id", "ts"),)


class AlertRecord(Base):
    """Persistent monitor alert events raised by deterministic rules."""

    __tablename__ = "alerts"

    alert_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    run_id: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("runs.run_id", ondelete="SET NULL"), nullable=True, index=True
    )
    device_id: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    rule: Mapped[str] = mapped_column(String(64), nullable=False)
    severity: Mapped[str] = mapped_column(String(32), nullable=False)
    observed: Mapped[str] = mapped_column(String(64), nullable=False)
    threshold: Mapped[str] = mapped_column(String(64), nullable=False)
    message: Mapped[str] = mapped_column(String(200), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )

    run: Mapped[RunRecord | None] = relationship(back_populates="alerts")
    diagnoses: Mapped[list[DiagnosisRecord]] = relationship(back_populates="alert")
    proposals: Mapped[list[ProposalRecord]] = relationship(back_populates="alert")


class DiagnosisRecord(Base):
    """Diagnostic findings produced by DiagnosisAgent."""

    __tablename__ = "diagnoses"

    diagnosis_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    alert_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("alerts.alert_id", ondelete="CASCADE"), nullable=False, index=True
    )
    device_id: Mapped[str] = mapped_column(String(16), nullable=False)
    cause: Mapped[str] = mapped_column(String(64), nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    evidence_json: Mapped[str] = mapped_column(Text, nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(32), nullable=False)
    model: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )

    alert: Mapped[AlertRecord] = relationship(back_populates="diagnoses")
    proposals: Mapped[list[ProposalRecord]] = relationship(back_populates="diagnosis")


class ProposalRecord(Base):
    """Remediation proposals formulated by RemediationAgent awaiting approval."""

    __tablename__ = "proposals"

    proposal_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    diagnosis_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("diagnoses.diagnosis_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    alert_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("alerts.alert_id", ondelete="CASCADE"), nullable=False, index=True
    )
    device_id: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    justification: Mapped[str] = mapped_column(String(300), nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="pending", nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )

    alert: Mapped[AlertRecord] = relationship(back_populates="proposals")
    diagnosis: Mapped[DiagnosisRecord] = relationship(back_populates="proposals")
    approval: Mapped[ApprovalRecordItem | None] = relationship(
        back_populates="proposal", uselist=False
    )
    execution: Mapped[ExecutionRecordItem | None] = relationship(
        back_populates="proposal", uselist=False
    )


class ApprovalRecordItem(Base):
    """Human-in-the-loop operator approval or rejection records (SEC-22, SEC-23)."""

    __tablename__ = "approvals"

    approval_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    proposal_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("proposals.proposal_id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
    )
    approver_id: Mapped[str] = mapped_column(String(64), nullable=False)
    decision: Mapped[str] = mapped_column(String(32), nullable=False)
    reason: Mapped[str | None] = mapped_column(String(300), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )

    proposal: Mapped[ProposalRecord] = relationship(back_populates="approval")


class ExecutionRecordItem(Base):
    """Remediation actions executed strictly against simulated device state (SEC-41, SEC-42)."""

    __tablename__ = "executions"

    execution_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    proposal_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("proposals.proposal_id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
    )
    device_id: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    details_json: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )

    proposal: Mapped[ProposalRecord] = relationship(back_populates="execution")


class AuditEventRecord(Base):
    """Immutable, append-only audit trail records with zero update or delete methods (SEC-70)."""

    __tablename__ = "audit_events"

    event_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    payload_json: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False, index=True
    )


class ApiKeyRecord(Base):
    """Hashed and salted API credentials enforcing role-based access control (SEC-20, SEC-21)."""

    __tablename__ = "api_keys"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    label: Mapped[str] = mapped_column(String(100), nullable=False)
    role: Mapped[str] = mapped_column(String(32), nullable=False)  # "viewer" or "approver"
    key_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    key_prefix: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    salt: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class LLMCallRecord(Base):
    """Auditing and token budget tracking for all language model inferences (SEC-36)."""

    __tablename__ = "llm_calls"

    call_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    model: Mapped[str] = mapped_column(String(64), nullable=False)
    input_tokens: Mapped[int] = mapped_column(Integer, nullable=False)
    output_tokens: Mapped[int] = mapped_column(Integer, nullable=False)
    latency_ms: Mapped[float] = mapped_column(Float, nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(32), nullable=False)
    prompt_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    outcome: Mapped[str] = mapped_column(
        String(32), nullable=False
    )  # "success", "retry", "failure"
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False, index=True
    )


class QuotaUsageRecord(Base):
    """Daily request and inference quota tracking per calendar day."""

    __tablename__ = "quota_usage"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    usage_date: Mapped[str] = mapped_column(String(16), unique=True, nullable=False, index=True)
    request_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    llm_call_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    tokens_used: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_updated: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        nullable=False,
    )
