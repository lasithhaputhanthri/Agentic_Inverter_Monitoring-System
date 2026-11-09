# Testing and style rules (always apply)

## Before every commit
Run `make check`. It must pass. If it does not, fix the cause. Never skip hooks with `--no-verify`.

## Test expectations
- Every new module has tests in the matching folder.
- Test the failure paths: invalid input, timeouts, malformed model output, quota exhaustion, unknown IDs.
- Use `FakeClock` and `FakeLLMClient`. Tests must never depend on wall-clock time or call a live model.
- Tests that need the MQTT broker or Docker are marked `integration`. If the service is unavailable, the test skips with a clear message. It must not fail silently.
- Never delete or weaken an existing test to make the suite pass. If a test is wrong, explain why in the report and ask the human before changing it.

## Style
- `ruff` for lint and formatting. `mypy --strict` for `iir.common` and `iir.monitor`.
- No `print` in library code. Use `logging`.
- No commented-out code, debug prints, or unused imports in commits.
- Keep names specific. Avoid `data`, `info`, `manager`, and `helper`.

## Reproducibility
- Every random process takes an explicit seed.
- Synthetic data fixtures are generated from a seed. Commit the generator, not large data files.
