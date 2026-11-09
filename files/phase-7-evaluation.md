---
description: Phase 7 - build the evaluation harness, metrics, and reproducible report; the held-out run requires human approval
---

# Phase 7: Evaluation

## Preconditions
- Phase 6 is DONE.
- Read `.agents/rules/60-testing-and-style.md` and the evaluation section of `AGENTS.md`.

## Steps
1. Create branch `phase/7-evaluation`.
2. Write `docs/evaluation/design.md` BEFORE any held-out run. It must include: the tuning and held-out seed ranges, the number of injections per fault type (at least 100 on the held-out split), the four conditions (rule-based, LLM with simulated approval, and the rule-based diagnoser as baseline), the matching rule, and the harm table. Matching rule: a diagnosis matches a fault if the device matches, the diagnosis time falls within [start minus 2 min, end plus 10 min], and the cause maps to the fault type.
3. Create `src/iir/evaluation/metrics.py` as pure functions:
   - detection latency (median, p95, and count undetected)
   - diagnosis precision and recall
   - harmful actions proposed and how many were blocked
   - tokens per alert (mean and p95) and total calls
   - false alarms per device-day on fault-free runs
   - the same metrics for the rule-based diagnoser
4. Create `src/iir/evaluation/harm_rules.py` with the harmful pairs. Example: `reset_relay` on `grid_sag` is harmful.
5. Create `src/iir/evaluation/harness.py`. It runs the simulator and fault plan per seed and condition, using FakeClock and writing to `data/eval/{run_id}/`. It uses a separate SQLite file, never the production database. Live LLM use requires `EVAL_USE_LIVE_LLM=true` and human approval.
6. Create `src/iir/evaluation/report.py`. It writes `docs/evaluation/results.md` and `docs/evaluation/results.json`. Include 95 percent bootstrap confidence intervals (1000 resamples), up to 10 failure cases per fault type (IDs and enum values only, no free text), and the limitations.
7. Add `make eval`. The held-out run requires the `--final` flag. `--final` writes a marker file, and the harness refuses to run the held-out seeds again without deleting that marker, which requires human approval.

## Acceptance tests
- Each metric has a hand-computed unit test.
- The matching rule handles boundaries: exactly 2 minutes before start and exactly 10 minutes after end.
- Every listed harmful pair is counted as harmful.
- Two runs with the fake LLM produce byte-identical `results.json`.
- Importing `evaluation` from a runtime module fails the dependency test.
- Without `--final`, the harness refuses the held-out seed range.

## CHECKPOINT (mandatory stop)
- Do not run the held-out split until the human has read `docs/evaluation/design.md` and approved it in writing.
- Do not change the design after the held-out run. If the design needs to change, stop and ask.
- A live-LLM condition needs explicit approval, a model name, a token cap, and at least 3 repeats to measure spread.

## Done
- Update `docs/progress.md`. Commit the design before the results. Write the report with the design timestamp, the results table, the reproducibility check, and the list of limitations (simulated data, simulated approval, LLM variance).
