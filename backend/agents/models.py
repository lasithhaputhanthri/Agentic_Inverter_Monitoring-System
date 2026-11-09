"""Pydantic data models for diagnosis and remediation agents.

Purpose: Enforces strict schemas, validation rules, and immutability on all LLM outputs.
Inputs: Raw JSON or model attributes generated during inference.
Outputs: Immutable, validated DiagnosisResult and ActionProposal instances.
"""

from __future__ import annotations

from enum import StrEnum
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator


class DiagnosisCause(StrEnum):
    """Enumeration of recognized diagnostic failure causes."""

    OVERHEATING = "overheating"
    GRID_SAG = "grid_sag"
    STUCK_RELAY = "stuck_relay"
    COMM_DROPOUT = "comm_dropout"
    UNKNOWN = "unknown"


class RemediationAction(StrEnum):
    """Enumeration of conservative, safe remediation actions."""

    REDUCE_LOAD = "reduce_load"
    RESET_RELAY = "reset_relay"
    SCHEDULE_INSPECTION = "schedule_inspection"
    NO_ACTION = "no_action"


class DiagnosisResult(BaseModel):
    """Structured, immutable diagnostic result produced by the diagnosis agent."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    device_id: str = Field(
        ...,
        pattern=r"^INV-\d{2}$",
        description="Target inverter device identifier",
    )
    cause: DiagnosisCause = Field(
        ...,
        description="Identified root cause of the incident",
    )
    confidence: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Confidence score between 0.0 and 1.0",
    )
    evidence: list[str] = Field(
        ...,
        min_length=1,
        max_length=3,
        description="List of 1 to 3 concise supporting factual observations (max 200 chars each)",
    )
    prompt_version: str = Field(
        ...,
        description="Version identifier of prompt template used",
    )
    model: str = Field(
        ...,
        description="Name of language model used for inference",
    )
    prompt_hash: str | None = Field(
        default=None,
        description="Cryptographic SHA-256 hash of prompt template",
    )

    @field_validator("evidence")
    @classmethod
    def validate_evidence_items(cls, items: list[str]) -> list[str]:
        """Ensure each evidence string does not exceed 200 characters."""
        for idx, item in enumerate(items):
            if len(item) > 200:
                raise ValueError(f"Evidence item {idx} exceeds maximum allowed length of 200 chars")
        return items


class ActionProposal(BaseModel):
    """Structured, immutable remediation proposal requiring operator approval before execution."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    proposal_id: UUID = Field(
        default_factory=uuid4,
        description="Unique proposal identifier",
    )
    device_id: str = Field(
        ...,
        pattern=r"^INV-\d{2}$",
        description="Target inverter device identifier matching the incident alert",
    )
    action: RemediationAction = Field(
        ...,
        description="Recommended remediation action",
    )
    justification: str = Field(
        ...,
        max_length=300,
        description="Engineering justification for proposed action (max 300 chars)",
    )
    diagnosis_ref: str = Field(
        ...,
        description="Reference identifier or cause of the associated diagnosis",
    )
    prompt_version: str = Field(
        ...,
        description="Version identifier of prompt template used",
    )
    model: str = Field(
        ...,
        description="Name of language model used for inference",
    )
    prompt_hash: str | None = Field(
        default=None,
        description="Cryptographic SHA-256 hash of prompt template",
    )
