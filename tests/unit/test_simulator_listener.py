"""Unit tests for the simulator command listener.

Purpose: Verifies command-triggered telemetry dispatch (MQTT poll/read command).
Inputs: Synthetic command payloads and mock MQTT clients.
Outputs: Assertion checks on response generation and publication.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from unittest.mock import MagicMock

from backend.common.clock import FakeClock
from backend.common.config import LimitsConfig, LoadConfig, MqttSettings, Settings, TokensConfig
from simulator.devices import make_fleet
from simulator.listener import SimulatorCommandListener
from simulator.publisher import TelemetryPublisher


def test_command_listener_dispatches_telemetry_on_poll() -> None:
    """When backend sends a read/poll command, simulator publishes inverter telemetry."""
    settings = Settings(
        app_env="test",
        mqtt_host="localhost",
        mqtt_port=1883,
        mqtt_username="simulator",
        mqtt_password="secret_password",
        mqtt_tls=False,
        api_key_pepper="test_pepper_long_phrase_min_32_chars",
        llm_api_key="test_llm_key",
        limits=LimitsConfig(),
        tokens=TokensConfig(),
        load=LoadConfig(),
        mqtt=MqttSettings(),
    )

    mock_client = MagicMock()
    mock_pub_client = MagicMock()
    mock_publisher = TelemetryPublisher(settings, client=mock_pub_client)

    fleet = make_fleet(5, seed=42)
    clock = FakeClock(datetime(2026, 6, 1, 12, 30, 0, tzinfo=UTC))

    listener = SimulatorCommandListener(
        settings=settings,
        fleet=fleet,
        clock=clock,
        publisher=mock_publisher,
        client=mock_client,
    )

    # Simulate backend sending a read_telemetry command to INV-01
    payload = json.dumps({"command": "read_telemetry"})
    telemetry = listener.handle_command("INV-01", payload)

    assert telemetry is not None
    assert telemetry.device_id == "INV-01"
    assert telemetry.ac_power_w > 0.0

    # Verify publisher sent message
    mock_pub_client.publish.assert_called_once()
    called_topic = mock_pub_client.publish.call_args[0][0]
    assert called_topic == "fleet/inverter/INV-01/telemetry"


def test_command_listener_ignores_unknown_device() -> None:
    """Unknown device command is ignored safely."""
    settings = Settings(
        app_env="test",
        api_key_pepper="test_pepper_long_phrase_min_32_chars",
        llm_api_key="test_llm_key",
        mqtt_password="test_pw",
    )
    listener = SimulatorCommandListener(settings=settings)
    result = listener.handle_command("INV-99", json.dumps({"command": "poll"}))
    assert result is None
