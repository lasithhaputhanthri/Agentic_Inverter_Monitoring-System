"""MQTT publisher for simulated fleet telemetry.

Purpose: Transmits validated telemetry frames to the MQTT broker over authenticated TLS/plain channels.
Inputs: Validated TelemetryMessage instances and broker configuration.
Outputs: Published messages on MQTT topics with QoS 1, or refused oversized payloads.
"""

from __future__ import annotations

import paho.mqtt.client as mqtt

from iir.common.config import Settings
from iir.common.logging import get_logger
from iir.common.schemas import TelemetryMessage

logger = get_logger(__name__)

MAX_MQTT_PAYLOAD_BYTES: int = 2048  # SEC-52: 2 KB maximum payload


class PayloadSizeError(ValueError):
    """Raised when an MQTT message exceeds the maximum allowed payload size."""

    pass


class TelemetryPublisher:
    """Publishes inverter telemetry to the fleet MQTT broker."""

    def __init__(self, settings: Settings, client: mqtt.Client | None = None) -> None:
        self._settings = settings
        self._max_payload_bytes = getattr(
            settings.mqtt, "max_payload_bytes", MAX_MQTT_PAYLOAD_BYTES
        )

        if client is not None:
            self._client = client
        else:
            self._client = mqtt.Client(
                mqtt.CallbackAPIVersion.VERSION2,
                client_id="iir_fleet_simulator",
            )
            if settings.mqtt_username and settings.mqtt_password:
                self._client.username_pw_set(
                    username=settings.mqtt_username,
                    password=settings.mqtt_password,
                )
            if settings.mqtt_tls:
                self._client.tls_set()

    def connect(self) -> None:
        """Connect to the configured MQTT broker."""
        logger.info(
            "Connecting to MQTT broker at %s:%d (TLS=%s)",
            self._settings.mqtt_host,
            self._settings.mqtt_port,
            self._settings.mqtt_tls,
        )
        self._client.connect(
            host=self._settings.mqtt_host,
            port=self._settings.mqtt_port,
            keepalive=60,
        )

    def disconnect(self) -> None:
        """Disconnect cleanly from the broker."""
        self._client.disconnect()

    def publish(self, message: TelemetryMessage) -> bool:
        """Publish a telemetry message to the appropriate device topic.

        Args:
            message: Validated TelemetryMessage to transmit.

        Returns:
            True if publication was queued successfully.

        Raises:
            PayloadSizeError: If the serialized JSON payload exceeds 2 KB (SEC-52).
        """
        payload = message.model_dump_json()
        encoded = payload.encode("utf-8")

        if len(encoded) > self._max_payload_bytes:
            logger.warning(
                "Refusing oversized MQTT payload (%d bytes > %d bytes) for device %s",
                len(encoded),
                self._max_payload_bytes,
                message.device_id,
            )
            raise PayloadSizeError(
                f"Payload size {len(encoded)} exceeds limit of {self._max_payload_bytes} bytes"
            )

        topic = f"fleet/inverter/{message.device_id}/telemetry"
        qos = getattr(self._settings.mqtt, "qos", 1)
        info = self._client.publish(topic, encoded, qos=qos)
        return info.rc == mqtt.MQTT_ERR_SUCCESS or info.rc == 0
