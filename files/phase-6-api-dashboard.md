---
description: Phase 6 - add the database, authenticated and rate-limited API with roles, and a Streamlit dashboard that reads only through the API
---

# Phase 6: Storage, API, and dashboard

## Preconditions
- Phase 5 is DONE.
- Read `.agents/rules/20-security.md`, `40-limits-and-load.md`, and `50-output-guard-and-input.md` first.

## Steps
1. Create branch `phase/6-api-dashboard`.
2. Create `src/iir/storage/models.py` with SQLAlchemy 2.x tables: runs, telemetry_samples (sampled, 7-day retention), alerts, diagnoses, proposals, approvals, executions, audit_events (append-only, no update or delete methods), api_keys (id, label, role, key_hash, key_prefix, created_at, revoked_at), llm_calls, and quota_usage.
3. Create `src/iir/storage/repositories.py` with one repository per aggregate. Queries are parameterized. Sort and filter fields come from an allowlist.
4. Add Alembic and a first migration.
5. Create `src/iir/api/auth.py`. Keys come from `secrets.token_urlsafe(32)`. Store only a salted hash. Show the key once, at creation. Create keys only through a CLI command (`make create-key ROLE=viewer|approver LABEL=...`), never through a route. Read the key from the `X-API-Key` header, look it up by prefix, and compare with `hmac.compare_digest`.
6. Create `src/iir/api/deps.py` with `require_viewer` and `require_approver`. Role checks live only here.
7. Create `src/iir/api/routes.py`:
   - `GET /v1/health` (no auth, status only)
   - `GET /v1/alerts` (filters and cursor, limit clamped to 200)
   - `GET /v1/alerts/{alert_id}`
   - `GET /v1/fleet/status`
   - `GET /v1/timeline?run_id=`
   - `GET /v1/proposals?status=pending`
   - `POST /v1/proposals/{proposal_id}/decision` (approver only; body validated; reason passed through the output scanner)
   - `GET /v1/usage`
8. Add the security middleware: generic error handler with request IDs, headers from SEC-10, CORS from an explicit list, docs disabled in production, body size limit, rate limits, quotas, and the output guard on every text response.
9. Create `src/iir/dashboard/app.py` (Streamlit). It reads only through the API, with a key from the environment. Views: fleet grid, alert list, and a timeline of one run. Approve and Reject buttons appear only for the approver role. Show model text as plain text.
10. Optional, only if the human asks: add `POST /v1/questions` for free-text operator questions, following `50-output-guard-and-input.md`. It must never approve or execute anything.

## Acceptance tests
- Auth: missing key returns 401, wrong key returns 401, revoked key returns 401, a viewer on the approve route returns 403, an approver returns 200.
- The database file contains no plain API key (search for the generated key).
- SQL injection in `device_id` and sort fields returns 422 or an empty list, never a trace.
- `limit=100000` is clamped to 200.
- A 1 MB body returns 413.
- A forced exception returns generic JSON with a request ID and no traceback.
- Security headers are present on every response.
- The 61st request in a minute returns 429.
- A fake key placed in a fake model response is redacted in the API response.
- A second decision returns 409 and writes an audit event.
- The dashboard has no import of `simulator`, `faults`, `executor`, or `storage`.

## Manual check
- `curl` without a key returns 401 and no data. Record the output.

## Checkpoints (stop and ask)
- Before creating the first real API key, ask the human to confirm where it will be stored.

## Done
- Update `docs/progress.md`. Commit in logical steps. Write the report with test counts per group, the database key-search result, and a text dump of one demo timeline.
