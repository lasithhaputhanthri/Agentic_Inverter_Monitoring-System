# 1. Telemetry Monitor is Deterministic (Not an LLM)

## Context
The solar inverter fleet consists of 20 simulated inverters generating telemetry readings every 15 seconds (amounting to 115,200 telemetry messages per 24-hour cycle). Solar inverter faults (such as overheating, grid sag, stuck relays, and communication dropouts) present distinct, well-defined physical patterns.

Using an LLM to continuously ingest and evaluate every telemetry frame would introduce significant operational drawbacks:
1. Prohibitive API token consumption and financial cost.
2. Unpredictable inference latency incompatible with near-real-time incident alerting.
3. Hallucination risk and nondeterministic variance in alert detection.

## Decision
The monitoring component (`src/iir/monitor/`) is implemented strictly as deterministic, rule-based software without any LLM involvement. Telemetry signals are evaluated against physical bounds and temporal signatures (such as temperature thresholds and voltage windows).

## Consequences
- **Positive**: 100% reproducible and deterministic alert generation with sub-millisecond evaluation latency.
- **Positive**: Zero LLM token spend for baseline monitoring.
- **Positive**: Clear auditability and testability of fault-detection logic.
- **Negative / Neutral**: Requires explicit heuristic models and threshold definitions for each known anomaly type.
