---
description: Run lint, type checks, tests, and security scans and report the results
---

# Check the project

1. Run `make lint`. Record the result.
2. Run `make type`. Record the result.
3. Run `make test`. Record the number passed, failed, and skipped, and list every skip with its reason.
4. Run `make security`. Record bandit, pip-audit, and gitleaks results. Any high-severity finding or any secret is a failure.
5. If anything failed, fix the cause in the code, not the test. If you cannot fix it inside the current task, report it and stop.
6. Show the summary in the report format from AGENTS.md.
