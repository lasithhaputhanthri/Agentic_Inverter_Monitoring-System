"""Unit tests for the TelemetryMonitor detector.

Purpose: Verifies rolling-window caching, cooldown enforcement, malformed message resilience,
         and unknown device rejection.
Inputs: Synthetic message streams, malformed payloads, and clock timestamps.
Outputs: Pytest assertions verifying end-to-end detector behavior.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from backend.common.config import MonitorConfig
from backend.common.errors import MonitorError
from backend.common.schemas import TelemetryMessage
from backend.monitor.detector import TelemetryMonitor
from backend.monitor.models import AlertSeverity, MonitorRule


def _make_reading(
    device_id: str = "INV-01",
    ts: datetime | None = None,
    power_w: float = 3000.0,
    grid_v: float = 230.0,
    temp_c: float = 45.0,
    relay: str = "closed",
) -> TelemetryMessage:
    return TelemetryMessage(
        device_id=device_id,
        ts=ts or datetime(2026, 6, 1, 12, 0, 0, tzinfo=UTC),
        ac_power_w=power_w,
        dc_voltage_v=400.0,
        grid_voltage_v=grid_v,
        temperature_c=temp_c,
        relay_state=relay,  # type: ignore[arg-type]
        status="normal",
    )


def test_monitor_persistent_fault_produces_one_alert_per_cooldown() -> None:
    """Acceptance test: A persistent fault produces one alert per cooldown window (300s)."""
    cfg = MonitorConfig(
        cooldown_seconds=300.0, grid_voltage_consecutive_readings=3, grid_voltage_threshold_v=207.0
    )
    monitor = TelemetryMonitor(config=cfg, known_devices=["INV-01"])

    t0 = datetime(2026, 6, 1, 12, 0, 0, tzinfo=UTC)

    # 1st reading (sag) - no alert
    alerts1 = monitor.update(_make_reading(grid_v=195.0, ts=t0), now=t0)
    assert len(alerts1) == 0

    # 2nd reading (sag) - no alert
    t1 = t0 + timedelta(seconds=15)
    alerts2 = monitor.update(_make_reading(grid_v=195.0, ts=t1), now=t1)
    assert len(alerts2) == 0

    # 3rd reading (sag) - first alert fired!
    t2 = t0 + timedelta(seconds=30)
    alerts3 = monitor.update(_make_reading(grid_v=195.0, ts=t2), now=t2)
    assert len(alerts3) == 1
    assert alerts3[0].rule == MonitorRule.GRID_VOLTAGE_LOW
    assert alerts3[0].severity == AlertSeverity.WARNING

    # Subsequent readings during cooldown (e.g. t = 45s, 60s, ..., 290s) must NOT produce new alert
    for step in range(3, 20):
        t_step = t0 + timedelta(seconds=15 * step)
        step_alerts = monitor.update(_make_reading(grid_v=195.0, ts=t_step), now=t_step)
        # Filter for grid voltage alerts
        grid_alerts = [a for a in step_alerts if a.rule == MonitorRule.GRID_VOLTAGE_LOW]
        assert len(grid_alerts) == 0, f"Unexpected alert during cooldown at t={t_step}"

    # After cooldown expires (t >= t2 + 300s = t0 + 330s)
    t_after_cooldown = t2 + timedelta(seconds=305)
    alerts_after = monitor.update(
        _make_reading(grid_v=195.0, ts=t_after_cooldown), now=t_after_cooldown
    )
    grid_after = [a for a in alerts_after if a.rule == MonitorRule.GRID_VOLTAGE_LOW]
    assert len(grid_after) == 1, "Expected a new alert after cooldown elapsed"


def test_monitor_malformed_message_dropped_and_counted() -> None:
    """Acceptance test: A malformed message is dropped and counted, and the stream continues."""
    monitor = TelemetryMonitor(known_devices=["INV-01"])
    t0 = datetime(2026, 6, 1, 12, 0, 0, tzinfo=UTC)

    # Valid message
    valid_msg = _make_reading(device_id="INV-01", ts=t0)
    assert monitor.update(valid_msg, now=t0) == []
    assert monitor.malformed_message_count == 0
    assert monitor.total_processed_count == 1

    # Malformed dictionary (missing required fields)
    bad_dict = {"device_id": "INV-01", "temperature_c": 500.0}
    assert monitor.update(bad_dict, now=t0) == []
    assert monitor.malformed_message_count == 1
    assert monitor.total_processed_count == 1  # Unchanged

    # Malformed JSON string
    bad_json = "NOT_A_JSON_STRING"
    assert monitor.update(bad_json, now=t0) == []
    assert monitor.malformed_message_count == 2

    # Malformed type
    assert monitor.update(12345, now=t0) == []
    assert monitor.malformed_message_count == 3

    # Subsequent valid message succeeds without hindrance
    t1 = t0 + timedelta(seconds=15)
    valid_msg2 = _make_reading(device_id="INV-01", ts=t1)
    monitor.update(valid_msg2, now=t1)
    assert monitor.total_processed_count == 2
    assert monitor.malformed_message_count == 3


def test_monitor_unknown_device_id_rejected() -> None:
    """Acceptance test: An unknown device ID is rejected."""
    monitor = TelemetryMonitor(known_devices=["INV-01", "INV-02"])
    t0 = datetime(2026, 6, 1, 12, 0, 0, tzinfo=UTC)

    # Device INV-03 is not in known_devices
    unknown_msg = _make_reading(device_id="INV-03", ts=t0)
    with pytest.raises(MonitorError, match="Rejected unknown device ID: INV-03"):
        monitor.update(unknown_msg, now=t0)


def test_monitor_rolling_window_bounded_at_10() -> None:
    """Verify monitor maintains maximum window of 10 readings per device."""
    monitor = TelemetryMonitor(known_devices=["INV-01"])
    t0 = datetime(2026, 6, 1, 12, 0, 0, tzinfo=UTC)

    for i in range(15):
        t = t0 + timedelta(seconds=15 * i)
        monitor.update(_make_reading(device_id="INV-01", ts=t), now=t)

    assert len(monitor.windows["INV-01"]) == 10
    # First reading in window should be reading index 5
    assert monitor.windows["INV-01"][0].ts == t0 + timedelta(seconds=15 * 5)
