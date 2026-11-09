---
description: Phase 3 - build the deterministic monitor and record the rule-based baseline; stop at the detection checkpoint
---

# Phase 3: Monitor (deterministic, no LLM)

## Preconditions
- Phase 2 is DONE.

## Steps
1. Create branch `phase/3-monitor`.
2. Create `src/iir/monitor/models.py` with `Alert`: `alert_id` (UUID), `device_id`, `ts`, `rule` (enum), `severity` (`info`, `warning`, `critical`), `observed`, `threshold`, and `message` (max 200 characters, built from a template only).
3. Create `src/iir/monitor/baseline_model.py` with a copy of the expected-temperature formula. Do not import from the simulator. Add a test that the two agree within 0.5 degrees across a grid of inputs.
4. Create `src/iir/monitor/rules.py` with pure functions for four rules:
   - `temp_high_for_power`: temperature minus expected is above 12 degrees for 3 readings in a row.
   - `grid_voltage_low`: grid voltage is below 207 V for 3 readings in a row.
   - `relay_mismatch`: relay is `open` while power is above 200 W for 2 readings in a row.
   - `device_silent`: no message for more than 60 seconds. Checked on a periodic tick.
   All thresholds come from `config/settings.yaml`.
5. Create `src/iir/monitor/detector.py`. It holds a rolling window of 10 readings per device, and its `update(message, now)` returns alerts. Apply a 300-second per-rule cooldown with `alerts.py`. Reject unknown device IDs. Re-validate every incoming message. Count and drop malformed messages without stopping the stream.
6. Log each alert with `run_id`, `alert_id`, `device_id`, and `rule`. Do not log the full payload.

## Acceptance tests
- Each rule fires on its condition, does not fire on one reading, and does not fire outside its window.
- A persistent fault produces one alert per cooldown window.
- A malformed message is dropped and counted, and the stream continues.
- An unknown device ID is rejected.
- `mypy --strict` passes on `monitor/`.

## Baselines (required deliverables)
- Fault-free 24-hour run: alerts per device-day. Save to `docs/baseline/monitor_v1_false_alarms.json`.
- Faulted run: detection rate and median latency for each fault type, using the ground-truth file through the evaluation helper in `tests/`. Save to `docs/baseline/monitor_v1_detection.json`.

## CHECKPOINT (mandatory stop)
- If any fault type is detected in fewer than 80 percent of injections, STOP. Do not start Phase 4.
- Report the numbers and propose rule changes. Record any change as an ADR in `docs/decisions/`.
- Only continue after the human approves the rule changes.

## Done
- Update `docs/progress.md`. Commit in logical steps. Write the report with both baseline files and the checkpoint result.
