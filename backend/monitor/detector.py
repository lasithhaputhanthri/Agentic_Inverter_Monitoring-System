"""Deterministic telemetry monitor and incident detector.

Purpose: Detects physical anomalies and fault conditions across inverter telemetry streams
         without relying on LLMs or external services.
Inputs: Validated or raw TelemetryMessage streams and simulation timestamps.
Outputs: Evaluated Alert instances subject to rolling-window thresholds and cooldowns.
"""

from __future__ import annotations

from collections import deque
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any

from pydantic import ValidationError

from backend.common.config import MonitorConfig
from backend.common.errors import MonitorError
from backend.common.logging import get_logger
from backend.common.schemas import TelemetryMessage
from backend.monitor.alerts import AlertCooldownTracker
from backend.monitor.models import Alert, AlertSeverity, MonitorRule
from backend.monitor.rules import (
    evaluate_device_silent,
    evaluate_grid_voltage_low,
    evaluate_relay_mismatch,
    evaluate_temp_high_for_power,
)

logger = get_logger(__name__)


class TelemetryMonitor:
    """Deterministic, rule-based monitor for the solar inverter fleet."""

    def __init__(
        self,
        config: MonitorConfig | None = None,
        known_devices: Sequence[str] | None = None,
        run_id: str = "default_run",
        start_time: datetime | None = None,
    ) -> None:
        self.config = config or MonitorConfig()
        self.known_devices = (
            set(known_devices)
            if known_devices is not None
            else {f"INV-{i:02d}" for i in range(1, 21)}
        )
        self.run_id = run_id
        self.start_time = (
            start_time.astimezone(UTC)
            if start_time is not None and start_time.tzinfo is not None
            else (start_time.replace(tzinfo=UTC) if start_time is not None else None)
        )

        self.windows: dict[str, deque[TelemetryMessage]] = {
            dev_id: deque(maxlen=self.config.window_size) for dev_id in self.known_devices
        }
        self.last_seen: dict[str, datetime] = {}
        self.cooldown_tracker = AlertCooldownTracker()
        self.malformed_message_count: int = 0
        self.total_processed_count: int = 0

    def _validate_input(self, raw_message: Any) -> TelemetryMessage | None:
        """Validate or re-validate any external telemetry message input."""
        try:
            if isinstance(raw_message, TelemetryMessage):
                # Re-validate model dump to ensure strict compliance
                return TelemetryMessage.model_validate(raw_message.model_dump())
            if isinstance(raw_message, dict):
                return TelemetryMessage.model_validate(raw_message)
            if isinstance(raw_message, str | bytes):
                return TelemetryMessage.model_validate_json(raw_message)
            return None
        except (ValidationError, ValueError, TypeError):
            return None

    def update(
        self,
        raw_message: Any,
        now: datetime | None = None,
    ) -> list[Alert]:
        """Process an incoming telemetry message and return any newly triggered alerts.

        Args:
            raw_message: Incoming TelemetryMessage, dict, or JSON string.
            now: Current simulation timestamp. If omitted, uses message ts.

        Returns:
            List of generated Alert instances.
        """
        msg = self._validate_input(raw_message)
        if msg is None:
            self.malformed_message_count += 1
            logger.warning(
                "[run_id=%s] Dropped malformed telemetry message (count=%d)",
                self.run_id,
                self.malformed_message_count,
            )
            return []

        if msg.device_id not in self.known_devices:
            logger.error("[run_id=%s] Rejected unknown device ID: %s", self.run_id, msg.device_id)
            raise MonitorError(f"Rejected unknown device ID: {msg.device_id}")

        self.total_processed_count += 1
        current_ts = now if now is not None else msg.ts
        current_utc = (
            current_ts.astimezone(UTC)
            if current_ts.tzinfo is not None
            else current_ts.replace(tzinfo=UTC)
        )

        # Update last seen and rolling buffer
        self.last_seen[msg.device_id] = msg.ts
        if msg.device_id not in self.windows:
            self.windows[msg.device_id] = deque(maxlen=self.config.window_size)
        self.windows[msg.device_id].append(msg)

        readings = list(self.windows[msg.device_id])
        alerts: list[Alert] = []

        # Rule 1: Temperature high for power
        temp_triggered, temp_obs, temp_thresh = evaluate_temp_high_for_power(
            readings=readings,
            threshold_delta_c=self.config.temp_delta_c,
            consecutive_readings=self.config.temp_consecutive_readings,
        )
        if temp_triggered and self.cooldown_tracker.can_alert(
            msg.device_id,
            MonitorRule.TEMP_HIGH_FOR_POWER,
            current_utc,
            self.config.cooldown_seconds,
        ):
            alert = Alert.create(
                device_id=msg.device_id,
                ts=current_utc,
                rule=MonitorRule.TEMP_HIGH_FOR_POWER,
                severity=AlertSeverity.WARNING,
                observed=temp_obs,
                threshold=temp_thresh,
            )
            self.cooldown_tracker.record_alert(
                msg.device_id, MonitorRule.TEMP_HIGH_FOR_POWER, current_utc
            )
            self._log_alert(alert)
            alerts.append(alert)

        # Rule 2: Grid voltage low
        grid_triggered, grid_obs, grid_thresh = evaluate_grid_voltage_low(
            readings=readings,
            threshold_v=self.config.grid_voltage_threshold_v,
            consecutive_readings=self.config.grid_voltage_consecutive_readings,
        )
        if grid_triggered and self.cooldown_tracker.can_alert(
            msg.device_id, MonitorRule.GRID_VOLTAGE_LOW, current_utc, self.config.cooldown_seconds
        ):
            alert = Alert.create(
                device_id=msg.device_id,
                ts=current_utc,
                rule=MonitorRule.GRID_VOLTAGE_LOW,
                severity=AlertSeverity.WARNING,
                observed=grid_obs,
                threshold=grid_thresh,
            )
            self.cooldown_tracker.record_alert(
                msg.device_id, MonitorRule.GRID_VOLTAGE_LOW, current_utc
            )
            self._log_alert(alert)
            alerts.append(alert)

        # Rule 3: Relay mismatch
        relay_triggered, relay_obs, relay_thresh = evaluate_relay_mismatch(
            readings=readings,
            power_threshold_w=self.config.relay_mismatch_power_w,
            consecutive_readings=self.config.relay_consecutive_readings,
        )
        if relay_triggered and self.cooldown_tracker.can_alert(
            msg.device_id, MonitorRule.RELAY_MISMATCH, current_utc, self.config.cooldown_seconds
        ):
            alert = Alert.create(
                device_id=msg.device_id,
                ts=current_utc,
                rule=MonitorRule.RELAY_MISMATCH,
                severity=AlertSeverity.CRITICAL,
                observed=relay_obs,
                threshold=relay_thresh,
            )
            self.cooldown_tracker.record_alert(
                msg.device_id, MonitorRule.RELAY_MISMATCH, current_utc
            )
            self._log_alert(alert)
            alerts.append(alert)

        # Also inspect timeouts for any silent devices at this timestamp
        alerts.extend(self.check_silence(current_utc))

        return alerts

    def check_silence(self, current_ts: datetime) -> list[Alert]:
        """Periodic tick evaluating device silence timeouts across all monitored inverters."""
        current_utc = (
            current_ts.astimezone(UTC)
            if current_ts.tzinfo is not None
            else current_ts.replace(tzinfo=UTC)
        )
        alerts: list[Alert] = []

        for dev_id in sorted(self.known_devices):
            last_ts = self.last_seen.get(dev_id, self.start_time)
            triggered, obs, thresh = evaluate_device_silent(
                last_seen_ts=last_ts,
                current_ts=current_utc,
                timeout_s=self.config.device_silent_timeout_s,
            )
            if triggered and self.cooldown_tracker.can_alert(
                dev_id, MonitorRule.DEVICE_SILENT, current_utc, self.config.cooldown_seconds
            ):
                alert = Alert.create(
                    device_id=dev_id,
                    ts=current_utc,
                    rule=MonitorRule.DEVICE_SILENT,
                    severity=AlertSeverity.WARNING,
                    observed=obs,
                    threshold=thresh,
                )
                self.cooldown_tracker.record_alert(dev_id, MonitorRule.DEVICE_SILENT, current_utc)
                self._log_alert(alert)
                alerts.append(alert)

        return alerts

    def _log_alert(self, alert: Alert) -> None:
        """Log an alert event conforming to SEC-09 (no full payload dumps)."""
        logger.warning(
            "[run_id=%s] Alert triggered: alert_id=%s device_id=%s rule=%s",
            self.run_id,
            str(alert.alert_id),
            alert.device_id,
            alert.rule.value,
        )
