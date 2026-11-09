"""Unit tests for the TelemetryMessage schema.

Purpose: Verifies bounds, strict forbidden extra fields, and regex constraints.
Inputs: Valid and invalid telemetry dictionaries.
Outputs: Assertion checks on Pydantic ValidationError.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from iir.common.schemas import TelemetryMessage


def test_temperature_500_rejected() -> None:
    """Schema: temperature 500 is rejected."""
    valid_payload = {
        "device_id": "INV-01",
        "ts": datetime(2026, 6, 1, 12, 0, 0, tzinfo=UTC),
        "ac_power_w": 2500.0,
        "dc_voltage_v": 450.0,
        "grid_voltage_v": 230.0,
        "temperature_c": 500.0,  # Invalid: max allowed is 120.0
        "relay_state": "closed",
        "status": "normal",
    }
    with pytest.raises(ValidationError) as exc_info:
        TelemetryMessage.model_validate(valid_payload)
    assert "temperature_c" in str(exc_info.value)


def test_extra_field_rejected() -> None:
    """Schema: an extra field is rejected (extra='forbid')."""
    payload_with_extra = {
        "device_id": "INV-01",
        "ts": datetime(2026, 6, 1, 12, 0, 0, tzinfo=UTC),
        "ac_power_w": 2500.0,
        "dc_voltage_v": 450.0,
        "grid_voltage_v": 230.0,
        "temperature_c": 45.0,
        "relay_state": "closed",
        "status": "normal",
        "unexpected_payload_field": "injected_data",
    }
    with pytest.raises(ValidationError) as exc_info:
        TelemetryMessage.model_validate(payload_with_extra)
    assert "extra_forbidden" in str(exc_info.value) or "unexpected_payload_field" in str(
        exc_info.value
    )


def test_invalid_device_id_rejected() -> None:
    """Device ID must conform to ^INV-\\d{2}$."""
    with pytest.raises(ValidationError):
        TelemetryMessage(
            device_id="INVERTER-999",
            ts=datetime(2026, 6, 1, 12, 0, 0, tzinfo=UTC),
            ac_power_w=100.0,
            dc_voltage_v=200.0,
            grid_voltage_v=230.0,
            temperature_c=30.0,
            relay_state="closed",
            status="normal",
        )
