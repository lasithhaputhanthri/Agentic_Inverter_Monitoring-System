"""Deterministic monitoring package."""

from backend.monitor.alerts import AlertCooldownTracker
from backend.monitor.baseline_model import calculate_expected_temperature
from backend.monitor.detector import TelemetryMonitor
from backend.monitor.models import Alert, AlertSeverity, MonitorRule
from backend.monitor.rules import (
    evaluate_device_silent,
    evaluate_grid_voltage_low,
    evaluate_relay_mismatch,
    evaluate_temp_high_for_power,
)

__all__ = [
    "Alert",
    "AlertCooldownTracker",
    "AlertSeverity",
    "MonitorRule",
    "TelemetryMonitor",
    "calculate_expected_temperature",
    "evaluate_device_silent",
    "evaluate_grid_voltage_low",
    "evaluate_relay_mismatch",
    "evaluate_temp_high_for_power",
]
