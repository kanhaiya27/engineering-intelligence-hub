# Archive — two-laptop period (2026-10-03 … 2026-10-05)

Since 2026-10-05 the project is built on one laptop (laptop-a) only (WORK_PLAN change C11).
These files document the earlier two-laptop period and are kept for history:

- `PROGRESS-B.md` — laptop-b's work log (its merged work is part of the project: escalation
  fix F1, retrieval labels for 36 tasks, API contract v1, Qdrant healthcheck).
- `SETUP_LAPTOP_B.md` — how laptop-b was set up (also documents restoring the Qdrant snapshot).
- `WORKFLOW_two_laptops.md` — the two-laptop branch/PR/ownership rules.

The two-laptop sync guard (`scripts/git_sync_guard.py`, its tests and the hooks in
`.claude/settings.json`) was removed; it is recoverable from git history (tag `pre-audit`).
