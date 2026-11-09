"""Fault injection data models and specifications.

Purpose: Defines immutable Pydantic schemas for injected faults and ground truth records.
Inputs: Fault parameters, device IDs, timestamps, and severity levels.
Outputs: Validated, immutable FaultSpec and GroundTruthRecord objects.
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, field_validator


class FaultType(StrEnum):
    """Enumeration of simulated fault types."""

    OVERHEATING = "overheating"
    GRID_SAG = "grid_sag"
    RELAY_STUCK = "relay_stuck"
    COMM_DROPOUT = "comm_dropout"


class FaultSpec(BaseModel):
    """Specification of an injected fault scenario."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    fault_id: str = Field(
        ...,
        pattern=r"^FLT-\d{4}$",
        description="Unique identifier for the fault event (e.g. FLT-0001)",
    )
    fault_type: FaultType = Field(
        ...,
        description="Classification of the fault condition",
    )
    device_id: str = Field(
        ...,
        pattern=r"^INV-\d{2}$",
        description="Target inverter device identifier",
    )
    start_ts: datetime = Field(
        ...,
        description="Timezone-aware UTC timestamp when the fault begins",
    )
    duration_s: float = Field(
        ...,
        gt=0.0,
        description="Duration of the fault condition in seconds",
    )
    severity: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Normalized severity factor between 0.0 and 1.0",
    )

    @field_validator("start_ts")
    @classmethod
    def validate_utc_timestamp(cls, v: datetime) -> datetime:
        """Ensure start timestamp has timezone info and is UTC."""
        if v.tzinfo is None:
            raise ValueError("Timestamp must be timezone-aware (UTC)")
        return v.astimezone(UTC)


class GroundTruthRecord(BaseModel):
    """Append-only ground truth audit log record for injected faults."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    fault_id: str = Field(..., pattern=r"^FLT-\d{4}$")
    fault_type: FaultType = Field(...)
    device_id: str = Field(..., pattern=r"^INV-\d{2}$")
    start_ts: datetime = Field(...)
    duration_s: float = Field(..., gt=0.0)
    severity: float = Field(..., ge=0.0, le=1.0)
    injected_at: datetime = Field(
        ...,
        description="Timezone-aware UTC timestamp when the fault was first injected into telemetry",
    )

    @field_validator("start_ts", "injected_at")
    @classmethod
    def validate_utc_timestamp(cls, v: datetime) -> datetime:
        """Ensure timestamps have timezone info and are UTC."""
        if v.tzinfo is None:
            raise ValueError("Timestamp must be timezone-aware (UTC)")
        return v.astimezone(UTC)

    @classmethod
    def from_fault(cls, fault: FaultSpec, injected_at: datetime) -> GroundTruthRecord:
        """Create a GroundTruthRecord from an existing FaultSpec and injection timestamp."""
        return cls(
            fault_id=fault.fault_id,
            fault_type=fault.fault_type,
            device_id=fault.device_id,
            start_ts=fault.start_ts,
            duration_s=fault.duration_s,
            severity=fault.severity,
            injected_at=injected_at,
        )
