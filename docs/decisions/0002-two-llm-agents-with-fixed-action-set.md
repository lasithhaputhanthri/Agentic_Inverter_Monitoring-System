# 2. Two LLM Agents with Fixed Action Set

## Context
When an alert is raised by the deterministic monitor, incident response requires two distinct analytical tasks:
1. Determining the probable root cause of the observed telemetry anomaly.
2. Formulating a safe, standard remediation proposal for human approval.

Allowing a single agent or unconstrained text generation could allow prompt injection attacks to hallucinate arbitrary operations, bypass safety checks, or generate destructive shell commands.

## Decision
We decouple incident handling into two sequential LLM agents operating under strict schemas with `extra="forbid"`:
1. **Diagnosis Agent**: Evaluates alert context and historical telemetry windows, selecting exactly one diagnosis from: `overheating`, `grid_sag`, `stuck_relay`, `comm_dropout`, or `unknown`.
2. **Remediation Agent**: Evaluates the diagnosed cause and selects exactly one proposal from: `reduce_load`, `reset_relay`, `schedule_inspection`, or `no_action`.

Neither agent possesses tool write permissions or execution capabilities. Action execution is handled exclusively by the separate executor following human approval.

## Consequences
- **Positive**: Strict bounding of LLM output prevents command injection or arbitrary action execution.
- **Positive**: Schema validation failures can be reliably handled with retries and fail-safe defaults (`unknown` / `no_action`).
- **Positive**: Human reviewers receive standardized, predictable proposal formats.
- **Negative / Neutral**: Novel or multi-factor faults cannot trigger bespoke composite actions outside the pre-approved enum set.
