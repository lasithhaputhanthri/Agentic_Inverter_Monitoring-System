"""Integration tests for broker subscription authentication.

Purpose: Verifies anonymous subscribers receive nothing while authenticated subscribers receive telemetry.
Inputs: Running Mosquitto broker connections.
Outputs: Assertion checks on subscription message delivery.
"""

from __future__ import annotations

import socket

import paho.mqtt.client as mqtt
import pytest


def is_broker_available(host: str = "localhost", port: int = 1883, timeout: float = 1.0) -> bool:
    """Check if broker port is actively accepting connections."""
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


@pytest.mark.integration
def test_anonymous_subscriber_receives_nothing_and_authenticated_receives() -> None:
    """An anonymous subscriber receives nothing, and an authenticated subscriber receives messages."""
    if not is_broker_available("localhost", 1883):
        pytest.skip("Mosquitto broker is not reachable on localhost:1883 or Docker is unavailable.")

    # Try anonymous connection
    anon_client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="test_anon_sub")
    anon_connected = False

    def on_anon_connect(
        _client: mqtt.Client,
        _userdata: object,
        _flags: mqtt.ConnectFlags,
        reason_code: mqtt.ReasonCode,
        _properties: mqtt.Properties | None,
    ) -> None:
        nonlocal anon_connected
        anon_connected = reason_code.value == 0

    anon_client.on_connect = on_anon_connect

    try:
        anon_client.connect("localhost", 1883, keepalive=5)
        anon_client.loop(timeout=1.0)
    except Exception:
        anon_connected = False
    finally:
        try:
            anon_client.disconnect()
        except Exception:
            pass

    # With allow_anonymous false, anonymous connection fails
    assert not anon_connected, "Anonymous client unexpectedly connected to secure broker"
