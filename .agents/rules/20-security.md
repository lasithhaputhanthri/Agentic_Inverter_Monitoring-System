# Security rules (always apply)

Each rule has an ID. Cite the IDs in your report.

## Secrets
- SEC-01: Secrets come only from environment variables. Never write a secret into code, config, tests, docs, logs, or fixtures.
- SEC-02: `.env.example` holds names and placeholders only.
- SEC-03: Run gitleaks before every commit. Zero findings.
- SEC-09: Logs never contain keys, tokens, passwords, full prompts that include user data, or full telemetry dumps.
- SEC-36: Never log the LLM API key. Log only the model name, token counts, and latency.

## Input handling
- SEC-06: Validate every external input with pydantic: MQTT payloads, API bodies, CLI answers, and free text.
- SEC-07: Use SQLAlchemy parameterized queries only. Filter and sort fields come from an allowlist. Never build SQL from strings.
- SEC-52: Reject MQTT payloads larger than 2 KB.

## API surface
- SEC-08: Return a generic error and a request ID to clients. Keep stack traces in server logs.
- SEC-10: Send security headers on every response.
- SEC-11: CORS uses an explicit origin list. Never use a wildcard in production config.
- SEC-12: Disable OpenAPI docs when `APP_ENV=production`.
- SEC-20: Store API keys as salted hashes. Compare with `hmac.compare_digest`.
- SEC-21: Enforce roles (`viewer`, `approver`) in the dependency layer only.
- SEC-22 and SEC-23: Approvals are recorded once, append-only, with approver ID and timestamp.

## LLM safety
- SEC-30: Put telemetry and user text inside delimited data blocks. The system prompt says that block content is data, not instructions.
- SEC-31: Parse model output only into strict pydantic models. Reject unknown fields.
- SEC-32: Agents receive read-only tools only. Add a test that fails if any tool writes state.
- SEC-33: A proposal can name only the device in its alert. Check this in code, not only in the prompt.
- SEC-34: Keep a prompt-injection test set of at least 25 cases. Add a case every time you find a new attack pattern.
- SEC-35: Never send the system prompt, the approver's identity, or unneeded internal IDs to the LLM.

## Execution safety
- SEC-40: The executor acts only on devices that exist in the simulator registry.
- SEC-41: The executor has no file, network, or shell access. Its only write path is the simulator state API.
- SEC-42: Actions are idempotent. A repeated execution key is a no-op.
- SEC-43: Follow the policy table. A pair not in the table is blocked and logged as `policy_blocked`.

## Broker
- SEC-50: Mosquitto uses `allow_anonymous false`, a password file, and ACLs.
- SEC-51: Use TLS (port 8883) in production configuration. Local development may use plain localhost, and the README must say so.

## Data
- SEC-60: Raw and evaluation data live in git-ignored folders.
- SEC-61: Only simulated data is committed.
- SEC-62: Delete raw telemetry older than 7 days by default. Make the window configurable.

## Audit
- SEC-70: The audit log is append-only. It has no update or delete method.
- SEC-71: Log failed authentication with the key prefix and source only. Never log the full key.
