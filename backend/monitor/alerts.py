"""Alert cooldown and rate-limiting tracking.

Purpose: Enforces per-rule, per-device quiet periods to prevent notification floods.
Inputs: Target device IDs, triggered rule types, timestamps, and cooldown durations.
Outputs: Cooldown authorization decisions and updated timestamp state.
"""

from __future__ import annotations

from datetime import UTC, datetime

from backend.monitor.models import MonitorRule


class AlertCooldownTracker:
    """Tracks per-device, per-rule alert dispatch timestamps to enforce cooldown periods."""

    def __init__(self) -> None:
        self._last_alert_time: dict[tuple[str, MonitorRule], datetime] = {}

    def can_alert(
        self,
        device_id: str,
        rule: MonitorRule,
        now: datetime,
        cooldown_s: float,
    ) -> bool:
        """Determine whether an alert for a device and rule is permitted under cooldown rules."""
        now_utc = now.astimezone(UTC) if now.tzinfo is not None else now.replace(tzinfo=UTC)
        key = (device_id, rule)

        if key in self._last_alert_time:
            last_ts = self._last_alert_time[key]
            elapsed_s = (now_utc - last_ts).total_seconds()
            if elapsed_s < cooldown_s:
                return False

        return True

    def record_alert(
        self,
        device_id: str,
        rule: MonitorRule,
        now: datetime,
    ) -> None:
        """Record an alert firing timestamp to initiate or reset the cooldown period."""
        now_utc = now.astimezone(UTC) if now.tzinfo is not None else now.replace(tzinfo=UTC)
        self._last_alert_time[(device_id, rule)] = now_utc

    def reset(self) -> None:
        """Clear all recorded alert timestamps."""
        self._last_alert_time.clear()
