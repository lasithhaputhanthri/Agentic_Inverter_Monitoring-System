"""Pydantic schemas for API request and response validation.

Purpose: Enforces SEC-06 and SEC-31:
         - Strict type-validation and rejection of unknown fields.
         - Clear data transfer contracts for endpoints.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class HealthResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: str = "healthy"
    service: str = "iir-backend"
    timestamp: datetime


class AlertResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="forbid")

    alert_id: str
    device_id: str
    rule: str
    severity: str
    observed: str
    threshold: str
    message: str
    ts: datetime
    run_id: str | None = None


class AlertListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[AlertResponse]
    next_cursor: str | None = None
    count: int


class InverterStatusResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    device_id: str
    status: str
    ac_power_w: float
    dc_voltage_v: float
    grid_voltage_v: float
    temperature_c: float
    relay_state: str
    last_seen: datetime | None = None


class FleetStatusResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    devices: list[InverterStatusResponse]
    total_active: int
    total_devices: int


class TimelineEventResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: str
    id: str
    timestamp: str
    summary: str
    device_id: str | None = None
    proposal_id: str | None = None


class ProposalResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="forbid")

    proposal_id: str
    diagnosis_id: str
    alert_id: str
    device_id: str
    action: str
    justification: str
    status: str
    created_at: datetime


class DecisionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decision: Literal["approve", "reject"]
    reason: str | None = Field(default=None, max_length=4000)


class DecisionResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: str
    proposal_id: str
    approval_id: str
    decision: str


class UsageResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    usage_date: str
    request_count: int
    llm_call_count: int
    tokens_used: int
    daily_request_limit: int = 2000
    daily_llm_limit: int = 200
    daily_token_limit: int = 1_000_000
