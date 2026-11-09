"""Action execution handlers targeting the simulator public state API.

Purpose: Executes approved remediation actions solely against the simulated fleet state.
Inputs: SimulatorStateAPI provider, target device identifier, and action parameters.
Outputs: Execution outcome dictionary recording state modifications.
"""

from __future__ import annotations

from typing import Any, Protocol

from backend.agents.models import RemediationAction


class SimulatorStateAPI(Protocol):
    """Protocol for interacting safely with simulated inverter fleet state (SEC-41)."""

    def has_device(self, device_id: str) -> bool:
        """Verify device existence in the simulator fleet registry."""
        ...

    def update_device_state(self, device_id: str, updates: dict[str, Any]) -> None:
        """Apply state updates to the simulated device."""
        ...

    def append_maintenance_note(self, device_id: str, note: str) -> None:
        """Append an inspection or maintenance record to the device state."""
        ...

    def get_device_state(self, device_id: str) -> dict[str, Any]:
        """Read the current simulation state dictionary for a device."""
        ...


def execute_reduce_load(api: SimulatorStateAPI, device_id: str) -> dict[str, Any]:
    """Action: reduce_load - sets load_scale to 0.7 in simulator state."""
    api.update_device_state(device_id, {"load_scale": 0.7})
    return {
        "action": RemediationAction.REDUCE_LOAD.value,
        "device_id": device_id,
        "load_scale": 0.7,
        "status": "applied",
    }


def execute_reset_relay(api: SimulatorStateAPI, device_id: str) -> dict[str, Any]:
    """Action: reset_relay - sets relay_state to closed in simulator state."""
    api.update_device_state(device_id, {"relay_state": "closed"})
    return {
        "action": RemediationAction.RESET_RELAY.value,
        "device_id": device_id,
        "relay_state": "closed",
        "status": "applied",
    }


def execute_schedule_inspection(
    api: SimulatorStateAPI, device_id: str, note: str = "Automated inspection scheduled"
) -> dict[str, Any]:
    """Action: schedule_inspection - appends maintenance record to device state."""
    api.append_maintenance_note(device_id, note)
    return {
        "action": RemediationAction.SCHEDULE_INSPECTION.value,
        "device_id": device_id,
        "note": note,
        "status": "applied",
    }


def execute_no_action(api: SimulatorStateAPI, device_id: str) -> dict[str, Any]:
    """Action: no_action - records a deliberate no-op."""
    return {
        "action": RemediationAction.NO_ACTION.value,
        "device_id": device_id,
        "status": "no_op",
    }
