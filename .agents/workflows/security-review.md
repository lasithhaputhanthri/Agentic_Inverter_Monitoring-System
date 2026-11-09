---
description: Review the current diff against the security rules and report each rule as pass or fail
---

# Security review of the current changes

1. Run `git diff --stat` and `git diff` for uncommitted changes, or `git log -p` for the current branch's commits.
2. For each rule in `.agents/rules/20-security.md`, decide whether the diff touches it. List the rules touched.
3. For each touched rule, check the code and its test. Mark PASS only when a test proves the control, not when the code merely looks right.
4. Check specifically for: secrets or credentials in any file, `.env` or `data/` files staged, string-built SQL, `eval`, `exec`, `subprocess`, `os.system`, unvalidated input, a missing role check on a route, and a log line that could contain a secret.
5. Run `make security`.
6. Report each finding with its file and line, its severity, and the fix. Do not commit fixes for security findings without showing them to the human first.
