"""Fault injection and append-only ground-truth tracking.

Purpose: Injects reproducible anomalies into inverter telemetry and logs ground truth.
Inputs: Base telemetry messages, fault schedules.
Outputs: Anomaly-injected telemetry messages and append-only ground truth records.
"""
