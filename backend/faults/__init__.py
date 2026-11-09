"""Fault injection and ground truth package."""

from backend.faults.active import get_active_fault_for_device, get_active_faults, is_fault_active
from backend.faults.injector import (
    FaultSession,
    apply_fault,
    inject_comm_dropout,
    inject_grid_sag,
    inject_overheating,
    inject_relay_stuck,
)
from backend.faults.models import FaultSpec, FaultType, GroundTruthRecord
from backend.faults.scheduler import plan_faults

__all__ = [
    "FaultSession",
    "FaultSpec",
    "FaultType",
    "GroundTruthRecord",
    "apply_fault",
    "get_active_fault_for_device",
    "get_active_faults",
    "inject_comm_dropout",
    "inject_grid_sag",
    "inject_overheating",
    "inject_relay_stuck",
    "is_fault_active",
    "plan_faults",
]
