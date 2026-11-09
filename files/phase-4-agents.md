---
description: Phase 4 - build the LLM diagnosis and remediation agents with schema validation, read-only tools, budgets, and injection tests
---

# Phase 4: Diagnosis and remediation agents

## Preconditions
- Phase 3 is DONE, and the human has approved the monitor checkpoint.
- Read `.agents/rules/30-llm-agents.md` and `.agents/rules/20-security.md` before writing code.

## Steps
1. Create branch `phase/4-agents`.
2. Create `src/iir/agents/llm_client.py` with the `LLMClient` protocol, `LLMResponse` (text, input_tokens, output_tokens, model, latency_ms), a `FakeLLMClient` for tests (scripted responses, call counter, simulated timeouts and malformed output), and a `ProviderLLMClient` stub. Do NOT call a live provider in this phase.
3. Create `src/iir/agents/prompts/diagnosis_v1.txt` and `remediation_v1.txt`. Compute and store a hash of each file. Follow the prompt rules in `30-llm-agents.md`.
4. Create `src/iir/agents/models.py` with `DiagnosisResult` (device_id, cause enum, confidence 0 to 1, evidence list of 1 to 3 strings of max 200 characters, prompt_version, model) and `ActionProposal` (device_id, action enum, justification max 300 characters, diagnosis_ref, prompt_version, model). Both use `extra="forbid"`.
5. Create `src/iir/agents/tools.py` with `get_recent_telemetry(device_id, minutes)` (minutes clamped to 1 to 30, at most 60 samples) and `get_fleet_snapshot(exclude_device_id)` (latest reading of up to 19 other devices, rounded). Keep a fixed registry. No write tools.
6. Create `src/iir/agents/diagnosis.py` and `src/iir/agents/remediation.py`. Each follows this order: build the delimited prompt, check quota and token budget, call the client, validate, retry once on failure, fall back to `unknown` or `no_action` on second failure, run the output scanner on free text, and store call metadata.
7. Add a cache keyed by the sanitized features, the prompt version, and the model name.

## Acceptance tests
- Schema: valid output passes. Extra fields, wrong enum values, out-of-range confidence, and device mismatch all fail.
- Retry: one malformed response followed by a valid one is accepted, with two calls counted.
- Failure: two malformed responses produce `unknown` or `no_action`, with `schema_failure` recorded.
- Budget: over-budget input is truncated. A call that is still over budget is never made.
- Quota: at the daily limit, the fake client records zero calls.
- Timeout: retried per policy, then recorded as `llm_unavailable`.
- Injection set: `tests/security/test_agent_injection.py` with at least 25 cases placed in telemetry, alert text, and fleet snapshot. None may change the schema or the device.
- Tool registry: no tool writes state.
- Cache: identical input reuses the result. A new prompt version invalidates it.

## Evaluation sets (synthetic only)
- Generate, from a seed, a tuning split of 20 alerts per fault type plus 20 false alarms, saved under `tests/eval/fixtures/tuning/`.
- Generate a separate held-out split from a different seed range. Do not run it in this phase, and do not use it for tuning.
- Run the diagnosis agent on the tuning split with the fake client. Save accuracy and the confusion matrix to `docs/baseline/diagnosis_v1.json`.

## CHECKPOINT (mandatory stop)
- Before any run that calls a live model, STOP and ask the human for approval, the model name, and a token cap.
- Do not run a live model unless the human approves in writing in this session.

## Done
- Update `docs/progress.md`. Commit in logical steps. Write the report with the injection case count and pass count, token use per alert (mean and max), and tuning-split accuracy.
