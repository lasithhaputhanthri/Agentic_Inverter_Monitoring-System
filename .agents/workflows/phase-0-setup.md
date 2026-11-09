---
description: Phase 0 - create the project skeleton, tooling, broker config, and CI with no business logic
---

# Phase 0: Setup

## Preconditions
- The repository exists and `docs/progress.md` lists Phase 0 as TODO or IN PROGRESS.

## Steps
1. Create a branch `phase/0-setup`.
2. Create the package layout from `.agents/rules/10-architecture.md`. Each package gets `__init__.py` with a docstring. Add no business logic.
3. Create `pyproject.toml` with pinned versions for: pydantic, pydantic-settings, paho-mqtt, fastapi, sqlalchemy, langgraph, pytest, ruff, mypy, bandit, pip-audit. Add a lockfile. Configure ruff, mypy (strict for `iir.common` and `iir.monitor`), and pytest.
4. Create a `Makefile` with targets `install`, `lint`, `type`, `test`, `security`, `check`, `run` (placeholder), and `broker-users`.
5. Create `.gitignore` covering `.env`, `data/raw/`, `data/eval/`, `*.db`, `__pycache__/`, `.mypy_cache/`, `.pytest_cache/`, and `*.log`.
6. Create `.env.example` with names and placeholders only: `MQTT_HOST`, `MQTT_PORT`, `MQTT_USERNAME`, `MQTT_PASSWORD`, `MQTT_TLS`, `API_KEY_PEPPER`, `LLM_PROVIDER`, `LLM_MODEL`, `LLM_API_KEY`, `APP_ENV`. Comment each line with where its value comes from.
7. Create `src/iir/common/config.py` with pydantic-settings. Secrets come from environment variables. Non-secret values come from `config/settings.yaml`. A missing required secret raises `ConfigError` naming the variable, never its value.
8. Create `src/iir/common/errors.py` with `IIRError` and `ConfigError`.
9. Create `src/iir/common/logging.py` with a `RedactingFilter` that redacts key-like strings and `password=` or `secret=` assignments.
10. Create `docker-compose.yml` and `config/mosquitto/mosquitto.conf` with `allow_anonymous false`, a password file, and an ACL file. The ACL lets the simulator write only to `fleet/#` and lets the monitor read only `fleet/#`. The `broker-users` target prompts for passwords with `getpass` and never writes them into the repo.
11. Create `config/settings.yaml` with sections `limits`, `tokens`, `load`, and `mqtt`, using the defaults in `.agents/rules/40-limits-and-load.md`.
12. Create `.pre-commit-config.yaml` with ruff, bandit, and gitleaks hooks.
13. Create `.github/workflows/ci.yml` that runs `make check` and gitleaks on every push.
14. Create `docs/decisions/0001-monitor-is-not-an-llm.md` and `docs/decisions/0002-two-llm-agents-with-fixed-action-set.md`. Each has Context, Decision, and Consequences sections.
15. Create `tests/unit/test_dependency_rules.py`. It parses imports under `src/iir/` and fails on any rule violation from the architecture rules.

## Acceptance tests
- `make check` passes on a fresh clone.
- gitleaks reports zero findings.
- A config load with a missing secret raises `ConfigError` without printing the value.
- The logging filter redacts a fake key and a `password=` assignment.
- The dependency rule test passes.
- Broker rejects an anonymous publish (integration test, skipped with a message if Docker is unavailable).

## Checkpoints (stop and ask)
- Before running `docker compose up` for the first time, ask the human to confirm the broker password setup.
- Before adding any dependency not listed in step 3.

## Done
- Update `docs/progress.md` with status DONE.
- Commit in logical steps, for example `chore: scaffold package layout`, `build: add pyproject and lockfile`, `feat(common): add settings and redacting logger`, `chore(broker): add mosquitto with auth and ACL`, `ci: add check workflow`, `docs: add first two ADRs`.
- Write the report.
