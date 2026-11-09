---
description: Phase 8 - write the README and security docs, run the final security review, and prepare the release; tag and push need human approval
---

# Phase 8: Write-up, review, and release

## Preconditions
- Phase 7 is DONE.

## Steps
1. Create branch `phase/8-release`.
2. Write `README.md` with these sections, in order:
   1. Title and a one-sentence summary that includes the word "simulated"
   2. Mermaid architecture diagram
   3. What it does and does not do (no real hardware; simulated data; LLM not validated for real diagnosis)
   4. Which parts are deterministic and which use an LLM, linking to the ADRs
   5. Results copied from `docs/evaluation/results.json` (every number must match)
   6. Failure cases (at least three per fault type)
   7. Security summary, linking to `docs/security.md`
   8. Limitations
   9. How to run: `make install`, `docker compose up -d`, `make run`, `make eval`, `make check`
   10. Demo (link to `docs/demo.md`)
   11. Project layout and the dependency rule
   12. Licence and a `SECURITY.md` with a contact for reporting issues
3. Write `docs/security.md`. Map every SEC ID from `20-security.md` to where it is implemented, the test that proves it, and its status. Mark any control with no test as "not implemented", with the reason. Do not claim a control without a test.
4. Write `docs/demo.md`: a two-minute script covering broker start, simulator start, one injected overheating fault, the alert, the diagnosis and evidence, the proposal waiting for approval, approval, the executed action, the audit log, and a rejected second proposal. Include a fallback recording in `docs/demo/`.
5. Write `docs/interview_notes.md` with five design decisions and the alternatives rejected, three failure cases and what changed, a production-readiness answer (PostgreSQL, Redis for limits and queues, TLS, SSO for approvers, a real device interface with its own safety checks, and a formal policy review), and an honest list of what the AI assistant wrote versus what the author designed.
6. Run `/security-review` on the whole repository and fix any PASS-blocking findings.
7. Run `make security` and `gitleaks detect --source . --log-opts="--all"`. If a secret appears in history, STOP and ask the human. Never rewrite history without approval.
8. Run the injection suites in `tests/security/` and record the pass counts.
9. Do a clean reproduction: clone into a new folder and follow the README exactly. Fix any step that fails by correcting the documentation.
10. Clean up dead code, unused imports, and debug output. Confirm `.gitignore` covers `data/raw/`, `data/eval/`, databases, and `.env`. Confirm no real site name, address, serial number, or personal contact detail appears anywhere, including history.

## Acceptance tests
- Every number in the README matches `results.json`.
- `docs/security.md` lists every SEC ID with a status and a test name.
- The clean reproduction succeeds from the README alone.
- The demo runs live once, and the fallback recording exists.

## CHECKPOINT (mandatory stop)
- Do not create the `v1.0.0` tag or push to any remote without explicit human approval in this session.

## Done
- Update `docs/progress.md`. Commit in logical steps. Write the report with the security scan results, injection pass counts, the clean reproduction summary, and the documentation fixes made during reproduction.
