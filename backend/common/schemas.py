"""Common schema definitions for IIR.

Purpose: Defines frozen Pydantic data models for cross-module messages.
Inputs: Raw message dictionaries or keyword arguments.
Outputs: Validated, immutable schema instances.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

RelayState = Literal["closed", "open"]
InverterStatus = Literal["normal", "warning", "error"]


class TelemetryMessage(BaseModel):
    """Telemetry reading published by a solar inverter."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    device_id: str = Field(
        ...,
        pattern=r"^INV-\d{2}$",
        description="Inverter device identifier matching INV-XX",
    )
    ts: datetime = Field(
        ...,
        description="Timezone-aware UTC timestamp of the measurement",
    )
    ac_power_w: float = Field(
        ...,
        ge=0.0,
        le=10000.0,
        description="Active AC power output in Watts (0 to 10000)",
    )
    dc_voltage_v: float = Field(
        ...,
        ge=0.0,
        le=1000.0,
        description="Array DC voltage in Volts (0 to 1000)",
    )
    grid_voltage_v: float = Field(
        ...,
        ge=0.0,
        le=300.0,
        description="Grid AC voltage in Volts (0 to 300)",
    )
    temperature_c: float = Field(
        ...,
        ge=-40.0,
        le=120.0,
        description="Inverter internal temperature in Celsius (-40 to 120)",
    )
    relay_state: RelayState = Field(
        ...,
        description="Internal AC disconnection relay state",
    )
    status: InverterStatus = Field(
        ...,
        description="Operational health status of the inverter",
    )

    @field_validator("ts")
    @classmethod
    def validate_utc_timestamp(cls, v: datetime) -> datetime:
        """Ensure timestamp has timezone info and is UTC."""
        if v.tzinfo is None:
            raise ValueError("Timestamp must be timezone-aware (UTC)")
        return v.astimezone(UTC)
