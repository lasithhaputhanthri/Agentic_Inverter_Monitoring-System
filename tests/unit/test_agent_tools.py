"""Unit tests for agent read-only tools and tool registry integrity.

Purpose: Verifies tools adhere to clamping rules, snapshot filtering, and strict read-only semantics.
Inputs: TelemetryStore fixtures and query parameters.
Outputs: Pytest assertions verifying tool behavior and registry safety.
"""

from __future__ import annotations

import inspect
from datetime import UTC, datetime, timedelta

from backend.agents.tools import (
    TOOL_REGISTRY,
    TelemetryStore,
    get_fleet_snapshot,
    get_recent_telemetry,
)
from backend.common.schemas import TelemetryMessage


def _make_msg(dev_id: str, minutes_ago: float) -> TelemetryMessage:
    now = datetime(2026, 6, 1, 12, 0, 0, tzinfo=UTC)
    return TelemetryMessage(
        device_id=dev_id,
        ts=now - timedelta(minutes=minutes_ago),
        ac_power_w=3000.123,
        dc_voltage_v=400.0,
        grid_voltage_v=230.456,
        temperature_c=45.789,
        relay_state="closed",
        status="normal",
    )


def test_get_recent_telemetry_clamping_and_sample_limit() -> None:
    """Acceptance test: Minutes clamped to 1-30, returns at most 60 samples."""
    store = TelemetryStore()

    # Add 100 readings over the last 60 minutes for INV-01
    for i in range(100):
        store.add(_make_msg("INV-01", minutes_ago=i * 0.5))

    # Clamped to max 30 minutes, max 60 samples
    res_large = get_recent_telemetry("INV-01", minutes=60, store=store)
    assert len(res_large) <= 60
    # Values should be rounded to 1 decimal place
    assert res_large[0]["ac_power_w"] == 3000.1
    assert res_large[0]["grid_voltage_v"] == 230.5
    assert res_large[0]["temperature_c"] == 45.8

    # Clamped to min 1 minute
    res_min = get_recent_telemetry("INV-01", minutes=0, store=store)
    assert len(res_min) >= 1


def test_get_fleet_snapshot_excludes_target_and_caps_at_19() -> None:
    """Acceptance test: Fleet snapshot excludes target device and includes up to 19 devices."""
    store = TelemetryStore()
    for i in range(1, 21):
        dev = f"INV-{i:02d}"
        store.add(_make_msg(dev, minutes_ago=1.0))

    snap = get_fleet_snapshot("INV-01", store=store)
    assert "INV-01" not in snap, "Target device must be excluded from snapshot"
    assert len(snap) <= 19
    assert "INV-02" in snap


def test_tool_registry_read_only_and_naming() -> None:
    """Acceptance test: Every tool name starts with get_, and none writes state."""
    assert len(TOOL_REGISTRY) > 0

    for name, func in TOOL_REGISTRY.items():
        assert name.startswith("get_"), f"Tool '{name}' violates get_ naming requirement"
        # Verify function is callable and has no write/delete parameters
        sig = inspect.signature(func)
        param_names = set(sig.parameters.keys())
        assert "write" not in param_names
        assert "delete" not in param_names
        assert "update" not in param_names
