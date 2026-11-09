---
description: Phase 2 - add the four injected faults and the append-only ground-truth log
---

# Phase 2: Fault injector and ground truth

## Preconditions
- Phase 1 is DONE.

## Steps
1. Create branch `phase/2-faults`.
2. Create `src/iir/faults/models.py` with a `FaultType` enum (`overheating`, `grid_sag`, `relay_stuck`, `comm_dropout`), a frozen `FaultSpec` (fault_id, type, device_id, start_ts, duration_s, severity between 0 and 1), and a `GroundTruthRecord` with the same fields plus `injected_at`.
3. Create `src/iir/faults/scheduler.py`. `plan_faults(fleet, seed, start, end, count_per_type)` is pure and reproducible. It never overlaps faults on one device, and it leaves at least 10 minutes between faults on one device. It rejects unknown device IDs with `FaultPlanError`.
4. Create `src/iir/faults/injector.py` with one pure function per fault type. Each takes a telemetry message and the active fault, and returns a modified message or `None` for dropout.
   - `overheating`: temperature 15 to 30 degrees above expected, ramping over 5 minutes, then holding.
   - `grid_sag`: grid voltage between 180 and 205 V, with small noise.
   - `relay_stuck`: relay reports `open` while expected power is over 200 W. Status becomes `warning`.
   - `comm_dropout`: nothing is published for that device during the fault.
5. Create `src/iir/faults/active.py`, a pure function that returns the faults active at a timestamp.
6. Create `src/iir/faults/groundtruth.py`, an append-only JSONL writer at `data/raw/ground_truth/{run_id}.jsonl`. It never rewrites lines. A record is written when the fault starts, so `injected_at` is accurate.
7. Connect the faults to the runner without changing the generator's public behaviour.

## Acceptance tests
- Each fault type produces its signature over a 1-hour simulated window.
- `plan_faults` is reproducible from its seed, with no overlaps and with 10-minute gaps.
- The writer appends and never rewrites a line (write twice, read back).
- Every ground-truth record matches a signature in the replay file.
- The monitor's input model has no field named `fault` or `ground_truth`.
- Reading the ground-truth file from any module other than `evaluation` or `tests` fails the dependency test.
- A plan of 100 faults across 20 devices over 7 simulated days has zero overlaps. Record the result.

## Checkpoints (stop and ask)
- If any fault type cannot produce its signature without changing the generator's public interface, stop and ask.

## Done
- Update `docs/progress.md`. Commit in logical steps. Write the report with the overlap test result and five sample ground-truth lines. Include only device IDs and times, with no site data.
