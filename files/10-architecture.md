# Architecture rules (always apply)

## Layout
Code lives in `src/iir/` with these packages: common, simulator, faults, monitor, agents, workflow, executor, guard, limits, storage, api, dashboard, evaluation. Tests live in `tests/unit`, `tests/integration`, `tests/security`, and `tests/eval`.

## Dependency direction (enforced by `tests/unit/test_dependency_rules.py`)
- `common` imports nothing from the project.
- `monitor` must not import `agents`, `workflow`, or `faults`.
- `api` and `dashboard` must not import `simulator`, `faults`, or `executor`.
- `dashboard` must not import `storage`. It calls the API only.
- `evaluation` is imported by nothing at runtime.
- Only `evaluation` and `tests` may read `faults.groundtruth`.

If a change needs to break one of these rules, stop and ask the human.

## Module style
- One responsibility per module. Name files for what they do.
- Keep files under about 300 lines and functions under about 40 lines. If a file grows past that, split it.
- Prefer pure functions. Side effects (MQTT, database, LLM, clock) sit at the edges and are passed in.
- No global mutable state.
- Put every threshold, limit, model name, and path in `config/settings.yaml`, loaded through `common/config.py`. Never hard-code them.
- Every cross-module data structure is a pydantic v2 model in `common/schemas.py` or the owning package's `models.py`.
- Raise typed errors from `common/errors.py`. Never raise a bare `Exception`.
- Get the time from `common/clock.py` (`SystemClock` or `FakeClock`). Never call `datetime.now()` directly.
- Use `logging`. Do not use `print` in library code.
- Type hints on all public functions.

## Debuggability
- Every module starts with a docstring stating its purpose, inputs, and outputs.
- Every log line carries `run_id`, and where relevant `device_id`, `alert_id`, and `proposal_id`.
- Anything that writes state has a `--dry-run` option.
- The pipeline has a replay mode that runs from a saved JSONL file with no broker.
