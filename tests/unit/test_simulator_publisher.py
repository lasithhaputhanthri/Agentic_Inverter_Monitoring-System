"""Unit tests for the MQTT telemetry publisher.

Purpose: Verifies payload size rejection (SEC-52) and credential redaction in logs (SEC-09).
Inputs: Mock MQTT client and telemetry messages.
Outputs: Assertion checks on size limits and log contents.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from unittest.mock import MagicMock

import pytest

from iir.common.config import LimitsConfig, LoadConfig, MqttSettings, Settings, TokensConfig
from iir.common.schemas import TelemetryMessage
from iir.simulator.publisher import PayloadSizeError, TelemetryPublisher


def create_test_settings(password: str = "secret_broker_password_12345") -> Settings:
    """Create test settings instance with a synthetic broker password."""
    return Settings(
        app_env="test",
        mqtt_host="localhost",
        mqtt_port=1883,
        mqtt_username="simulator",
        mqtt_password=password,
        mqtt_tls=False,
        api_key_pepper="test_pepper_min_32_characters_long",
        llm_api_key="test_llm_key",
        limits=LimitsConfig(),
        tokens=TokensConfig(),
        load=LoadConfig(),
        mqtt=MqttSettings(max_payload_bytes=2048),
    )


def test_publisher_refuses_oversized_payload() -> None:
    """Publisher: an oversized payload is refused."""
    mock_client = MagicMock()
    settings = create_test_settings()
    # Force max payload bytes to 50 bytes to test refusal threshold safely
    settings.mqtt.max_payload_bytes = 50
    publisher = TelemetryPublisher(settings, client=mock_client)

    msg = TelemetryMessage(
        device_id="INV-01",
        ts=datetime(2026, 6, 1, 12, 0, 0, tzinfo=UTC),
        ac_power_w=3000.0,
        dc_voltage_v=450.0,
        grid_voltage_v=230.0,
        temperature_c=45.0,
        relay_state="closed",
        status="normal",
    )

    with pytest.raises(PayloadSizeError) as exc_info:
        publisher.publish(msg)

    assert "exceeds limit" in str(exc_info.value)
    mock_client.publish.assert_not_called()


def test_password_never_appears_in_logs(caplog: pytest.LogCaptureFixture) -> None:
    """The password never appears in captured logs."""
    synthetic_pw = "super_secret_broker_password_abc123"
    settings = create_test_settings(password=synthetic_pw)
    mock_client = MagicMock()

    with caplog.at_level(logging.DEBUG):
        publisher = TelemetryPublisher(settings, client=mock_client)
        publisher.connect()

        msg = TelemetryMessage(
            device_id="INV-02",
            ts=datetime(2026, 6, 1, 12, 0, 0, tzinfo=UTC),
            ac_power_w=2000.0,
            dc_voltage_v=400.0,
            grid_voltage_v=230.0,
            temperature_c=42.0,
            relay_state="closed",
            status="normal",
        )
        publisher.publish(msg)

    # Check all captured log output
    full_log = caplog.text
    assert synthetic_pw not in full_log
