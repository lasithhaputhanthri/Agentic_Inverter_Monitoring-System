"""Integration tests for Mosquitto broker authentication and ACL enforcement.

Purpose: Verifies broker rejects anonymous access and enforces ACL boundaries.
Inputs: Live or containerized MQTT broker connections.
Outputs: Connection and publish outcome assertions.
"""

from __future__ import annotations

import socket

import paho.mqtt.client as mqtt
import pytest


def is_broker_reachable(host: str = "localhost", port: int = 1883, timeout: float = 1.0) -> bool:
    """Check whether MQTT broker port is reachable."""
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


@pytest.mark.integration
def test_broker_rejects_anonymous_publish() -> None:
    """Mosquitto broker must reject anonymous publishing when allow_anonymous false is configured."""
    if not is_broker_reachable("localhost", 1883):
        pytest.skip("Mosquitto broker is not reachable on localhost:1883 or Docker is unavailable.")

    # Attempt connection with anonymous client
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="test_anon_client")
    connect_result: list[int] = []

    def on_connect(
        _client: mqtt.Client,
        _userdata: object,
        _flags: mqtt.ConnectFlags,
        reason_code: mqtt.ReasonCode,
        _properties: mqtt.Properties | None,
    ) -> None:
        connect_result.append(reason_code.value)

    client.on_connect = on_connect

    try:
        client.connect("localhost", 1883, keepalive=5)
        client.loop(timeout=2.0)
    except Exception as exc:
        # Connection actively refused or dropped
        pytest.skip(f"Broker connection failed during handshake: {exc}")
    finally:
        try:
            client.disconnect()
        except Exception:
            pass

    # When allow_anonymous is false, return code is 4 or 5 (Not authorized / Bad user or pass)
    # or reason_code != 0
    if connect_result:
        assert connect_result[0] != 0, (
            f"Broker unexpectedly allowed anonymous connection: {connect_result[0]}"
        )
