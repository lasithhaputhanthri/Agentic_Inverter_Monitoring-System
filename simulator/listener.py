"""Command listener and responder for the inverter simulator.

Purpose: Listens for poll/read commands from the backend over MQTT (or Modbus) and returns inverter telemetry.
Inputs: Inbound commands on fleet/inverter/{device_id}/command.
Outputs: Published TelemetryMessage responses on fleet/inverter/{device_id}/telemetry.
"""

from __future__ import annotations

import json
import re
from typing import Any, Protocol

import paho.mqtt.client as mqtt
from backend.common.clock import Clock, SystemClock
from backend.common.config import Settings
from backend.common.logging import get_logger
from backend.common.schemas import TelemetryMessage

from simulator.devices import DeviceProfile, make_fleet
from simulator.generator import next_telemetry
from simulator.publisher import TelemetryPublisher

logger = get_logger(__name__)

COMMAND_TOPIC_PATTERN: re.Pattern[str] = re.compile(r"^fleet/inverter/(INV-\d{2})/command$")


class CommandTransport(Protocol):
    """Abstract protocol for receiving poll/read commands (MQTT or Modbus)."""

    def start(self) -> None:
        """Start listening for commands."""
        ...

    def stop(self) -> None:
        """Stop listening."""
        ...


class SimulatorCommandListener:
    """Handles incoming read/poll commands and dispatches telemetry responses."""

    def __init__(
        self,
        settings: Settings,
        fleet: list[DeviceProfile] | None = None,
        clock: Clock | None = None,
        publisher: TelemetryPublisher | None = None,
        client: mqtt.Client | None = None,
    ) -> None:
        self.settings = settings
        self.fleet_map: dict[str, DeviceProfile] = {
            p.device_id: p for p in (fleet or make_fleet(20))
        }
        self.clock = clock or SystemClock()
        self.publisher = publisher or TelemetryPublisher(settings)

        if client is not None:
            self._client = client
        else:
            self._client = mqtt.Client(
                mqtt.CallbackAPIVersion.VERSION2,
                client_id="iir_simulator_listener",
            )
            if settings.mqtt_username and settings.mqtt_password:
                self._client.username_pw_set(
                    username=settings.mqtt_username,
                    password=settings.mqtt_password,
                )
            if settings.mqtt_tls:
                self._client.tls_set()

        self._client.on_message = self._on_message
        self._client.on_connect = self._on_connect

    def _on_connect(
        self,
        client: mqtt.Client,
        _userdata: object,
        _flags: mqtt.ConnectFlags,
        reason_code: mqtt.ReasonCode,
        _properties: mqtt.Properties | None,
    ) -> None:
        if reason_code.value == 0:
            logger.info("Simulator listener connected to broker. Subscribing to command topics...")
            client.subscribe("fleet/inverter/+/command", qos=1)
        else:
            logger.error("Simulator listener connection rejected: %s", reason_code)

    def handle_command(self, device_id: str, payload_str: str) -> TelemetryMessage | None:
        """Process a read command for a specific inverter and return telemetry."""
        profile = self.fleet_map.get(device_id)
        if not profile:
            logger.warning("Received command for unknown device: %s", device_id)
            return None

        # Parse command JSON
        try:
            data: dict[str, Any] = json.loads(payload_str)
        except json.JSONDecodeError:
            data = {"command": payload_str.strip()}

        command_type = data.get("command", "read_telemetry")
        if command_type in ("read_telemetry", "poll", "poll_telemetry"):
            import random

            rng = random.Random()  # nosec: B311
            ts = self.clock.now()
            telemetry = next_telemetry(profile, state=None, ts=ts, rng=rng)
            self.publisher.publish(telemetry)
            logger.info("Responded to '%s' command for %s", command_type, device_id)
            return telemetry

        logger.info("Ignored unhandled command type '%s' for %s", command_type, device_id)
        return None

    def _on_message(
        self,
        _client: mqtt.Client,
        _userdata: object,
        msg: mqtt.MQTTMessage,
    ) -> None:
        match = COMMAND_TOPIC_PATTERN.match(msg.topic)
        if not match:
            return

        device_id = match.group(1)
        try:
            payload_str = msg.payload.decode("utf-8")
        except UnicodeDecodeError:
            return

        self.handle_command(device_id, payload_str)

    def start(self) -> None:
        """Connect and begin listening in non-blocking network loop."""
        self.publisher.connect()
        self._client.connect(
            host=self.settings.mqtt_host,
            port=self.settings.mqtt_port,
            keepalive=60,
        )
        self._client.loop_start()
        logger.info("Simulator command listener started.")

    def stop(self) -> None:
        """Stop listening and disconnect cleanly."""
        self._client.loop_stop()
        self._client.disconnect()
        self.publisher.disconnect()
        logger.info("Simulator command listener stopped.")
