# Project progress

Update this file at the start and end of every task. Mark a phase DONE only after its acceptance tests pass and the report is written.

| Phase | Workflow | Status | Tag | Notes |
|---|---|---|---|---|
| 0 | /phase-0-setup | DONE | phase-0-setup | Skeleton, tooling, broker config, CI, ADRs |
| 1 | /phase-1-simulator | DONE | phase-1-simulator | 20-device MQTT simulator, curves, runner, replay |
| 2 | /phase-2-faults | DONE | phase-2-faults | 4 injected fault types, pure scheduler, append-only ground truth |
| 3 | /phase-3-monitor | DONE | phase-3-monitor | Deterministic monitor, 100% detection baseline, 0.0 false alarms |
| 4 | /phase-4-agents | DONE | phase-4-agents | LLM client protocol, diagnosis & remediation agents, injection test suite (26 cases), tuning baseline |
| 5 | /phase-5-approval-executor | TODO | | |
| 6 | /phase-6-api-dashboard | TODO | | |
| 7 | /phase-7-evaluation | TODO | | Held-out run needs human approval |
| 8 | /phase-8-release | TODO | | Tag and push need human approval |

## Current task
/phase-4-agents: Diagnosis and remediation agents completed; ready for Phase 5 (Approval gate and executor)

## Decisions and blockers
(none)
