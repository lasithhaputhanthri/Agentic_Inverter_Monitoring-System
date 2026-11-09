"""Data models for deterministic monitoring and alerts.

Purpose: Defines immutable alert schemas, rules, severities, and templated messages.
Inputs: Rule evaluation results, device IDs, timestamps, and observed metric values.
Outputs: Validated, immutable Alert instances.
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator


class MonitorRule(StrEnum):
    """Enumeration of deterministic monitoring rules."""

    TEMP_HIGH_FOR_POWER = "temp_high_for_power"
    GRID_VOLTAGE_LOW = "grid_voltage_low"
    RELAY_MISMATCH = "relay_mismatch"
    DEVICE_SILENT = "device_silent"


class AlertSeverity(StrEnum):
    """Enumeration of alert severity classifications."""

    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


ALERT_MESSAGE_TEMPLATES: dict[MonitorRule, str] = {
    MonitorRule.TEMP_HIGH_FOR_POWER: (
        "Inverter {device_id} temperature {observed}C exceeds expected by >{threshold}C for 3 consecutive readings."
    ),
    MonitorRule.GRID_VOLTAGE_LOW: (
        "Inverter {device_id} grid voltage {observed}V below allowable threshold {threshold}V for 3 readings."
    ),
    MonitorRule.RELAY_MISMATCH: (
        "Inverter {device_id} relay open while active power exceeds {threshold}W for 2 consecutive readings."
    ),
    MonitorRule.DEVICE_SILENT: (
        "Inverter {device_id} silent for {observed:.1f}s (threshold: {threshold:.1f}s)."
    ),
}


def build_alert_message(
    rule: MonitorRule,
    device_id: str,
    observed: float | str,
    threshold: float | str,
) -> str:
    """Construct an alert message strictly using predefined templates, capped at 200 characters."""
    template = ALERT_MESSAGE_TEMPLATES.get(rule, "Alert triggered on {device_id}: {observed}")
    if (
        rule == MonitorRule.DEVICE_SILENT
        and isinstance(observed, int | float)
        and isinstance(threshold, int | float)
    ):
        msg = template.format(
            device_id=device_id, observed=float(observed), threshold=float(threshold)
        )
    else:
        msg = template.format(device_id=device_id, observed=observed, threshold=threshold)
    return msg[:200]


class Alert(BaseModel):
    """Immutable incident alert raised by the deterministic telemetry monitor."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    alert_id: UUID = Field(
        default_factory=uuid4,
        description="Unique identifier for this alert occurrence",
    )
    device_id: str = Field(
        ...,
        pattern=r"^INV-\d{2}$",
        description="Target inverter device identifier",
    )
    ts: datetime = Field(
        ...,
        description="Timezone-aware UTC timestamp when the alert condition was detected",
    )
    rule: MonitorRule = Field(
        ...,
        description="Monitoring rule that triggered the alert",
    )
    severity: AlertSeverity = Field(
        ...,
        description="Severity level of the triggered condition",
    )
    observed: float | str = Field(
        ...,
        description="Observed metric value or state that triggered the rule",
    )
    threshold: float | str = Field(
        ...,
        description="Reference threshold against which the observation was compared",
    )
    message: str = Field(
        ...,
        max_length=200,
        description="Human-readable alert description built from standard template only",
    )

    @field_validator("ts")
    @classmethod
    def validate_utc_timestamp(cls, v: datetime) -> datetime:
        """Ensure alert timestamp has timezone info and is UTC."""
        if v.tzinfo is None:
            raise ValueError("Alert timestamp must be timezone-aware (UTC)")
        return v.astimezone(UTC)

    @classmethod
    def create(
        cls,
        device_id: str,
        ts: datetime,
        rule: MonitorRule,
        severity: AlertSeverity,
        observed: float | str,
        threshold: float | str,
        alert_id: UUID | None = None,
    ) -> Alert:
        """Factory creating an Alert with templated message."""
        msg = build_alert_message(rule, device_id, observed, threshold)
        return cls(
            alert_id=alert_id or uuid4(),
            device_id=device_id,
            ts=ts,
            rule=rule,
            severity=severity,
            observed=observed,
            threshold=threshold,
            message=msg,
        )
