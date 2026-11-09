---
description: Phase 5 - connect monitor and agents through a LangGraph workflow with a mandatory approval gate and an isolated executor
---

# Phase 5: Workflow, approval gate, and executor

## Preconditions
- Phase 4 is DONE.
- Read `.agents/rules/20-security.md` (SEC-22, SEC-23, SEC-33, SEC-40 to SEC-43, SEC-70) before writing code.

## Steps
1. Create branch `phase/5-approval-executor`.
2. Create `config/policy.yaml` with the allowed pairs:
   - overheating: reduce_load, schedule_inspection, no_action
   - grid_sag: schedule_inspection, no_action
   - stuck_relay: reset_relay, schedule_inspection, no_action
   - comm_dropout: schedule_inspection, no_action
   - unknown: no_action, schedule_inspection
   Create `src/iir/executor/policy.py` to load it. Any pair not in the table is blocked. `reset_relay` for `grid_sag` must be blocked.
3. Create `src/iir/workflow/approval.py`. An approval record holds proposal_id, approver_id, decision, optional reason (max 300 characters, scanned before storage), and timestamp. A proposal can be decided once. Approvals expire after 30 minutes, and expired proposals are never executed.
4. Create `src/iir/executor/actions.py` and `executor.py`. Before doing anything, the executor checks: an approval exists and says `approve`; the proposal has not already executed; the device exists in the simulator registry; the action is in the enum; the policy still allows the pair; the device-level rate limit (1 action per device per hour) is not exceeded; and the proposal's device matches the alert's device.
   - `reduce_load` sets `load_scale` to 0.7 in simulator state.
   - `reset_relay` sets `relay_state` to `closed` (only reachable for `stuck_relay` by policy).
   - `schedule_inspection` appends a maintenance note.
   - `no_action` records a no-op.
   The executor writes state only through the simulator's public state method. It has no file, network, or shell access, and it must not import `os`, `subprocess`, `socket`, or `open`-based writers.
5. Use an `execution_key` equal to the proposal ID. A repeat returns the stored result and changes nothing.
6. Create `src/iir/workflow/graph.py` with LangGraph. Nodes in order: ingest_alert, check_limits, diagnose, propose, policy_check, await_approval (interrupt), execute_or_reject, record. Use a SQLite checkpointer so state survives a restart.
7. Define the `AuditSink` protocol. Event types: alert_raised, diagnosis_made, proposal_made, policy_blocked, approval_requested, approved, rejected, expired, executed, execution_refused. Payloads contain IDs and enum values only, never free text.
8. Connect approval to a CLI prompt using `ask_decision` from `common/prompts.py`. Record the operator name.

## Acceptance tests
- Structural: walking the graph shows no path from propose to execute_or_reject that skips await_approval.
- Property: over 500 random alerts with random agent outputs (fake LLM), zero executions happen without an approval record.
- Approval: a second decision is refused and logged. An expired approval is never executed. A rejected proposal is never executed.
- Policy: `reset_relay` for `grid_sag` is blocked and logged as `policy_blocked`.
- Executor: unknown devices are refused. Mismatched devices are refused. A duplicate execution key is a no-op. The rate limit blocks a second action within an hour.
- Isolation: patch `open`, `socket`, and `subprocess` to raise. A valid action still succeeds. The executor module does not import those libraries.
- Restart: stop at await_approval, create a new graph with the same checkpointer, and resume with the same approval.

## Demo
- Run one alert from detection to approval prompt to execution or rejection. Print the audit log. Save it to `docs/demo/phase5_audit.txt`, with no site data.

## Checkpoints (stop and ask)
- Any change to `config/policy.yaml` needs human approval.
- Any test that would need to weaken the approval gate must be escalated, not changed.

## Done
- Update `docs/progress.md`. Commit in logical steps. Write the report with the property-test result (runs and unapproved executions, which must be zero), the structural test output, and the demo audit log.
