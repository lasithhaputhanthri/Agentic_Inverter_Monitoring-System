---
description: Find the next unfinished phase in docs/progress.md and run it, stopping at checkpoints
---

# Run the next phase

1. Read `docs/progress.md`. Find the first phase whose status is not DONE.
2. If every phase is DONE, report that and stop.
3. If the phase is BLOCKED, report the blocker from the Decisions section and stop.
4. Set that phase's status to IN PROGRESS in `docs/progress.md`.
5. Run the phase's workflow (the slash command in the table), following every step in it.
6. If the workflow reaches a checkpoint or a stop condition from AGENTS.md, stop, set the status to BLOCKED with the reason, and report to the human.
7. If the phase's acceptance tests all pass, set the status to DONE, record the tag name, and write the report from AGENTS.md.
8. Do not start the next phase in the same run. Stop after one phase and wait for the human.
