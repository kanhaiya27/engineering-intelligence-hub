"""
Engineering Intelligence Hub — two-laptop git sync guard (Claude Code hooks)
============================================================================
Both laptops push to the same GitHub repository at the same time. This script
keeps a Claude session on either laptop from working on stale code.

  session   SessionStart hook. `git fetch`, then report what the other laptop
            merged into origin/master that this checkout does not have yet.
            Output goes into Claude's context and, when something is missing,
            a warning is shown to the user.

  pretool   PreToolUse hook for Edit|Write. Blocks edits to files inside this
            repository while origin/master contains a MUST-PULL change that the
            current branch does not have. Uses the refs from the last fetch (no
            network), so it is fast.

A change is MUST-PULL when a commit on origin/master that HEAD lacks either
  * has "[must-pull]" in its message, or
  * touches a shared file (SHARED_PREFIXES below — the files both laptops depend on).

Unblock with `git checkout master; git pull` (on master) or
`git fetch; git merge origin/master` (on a feature branch). Never rebase or
force-push: history is never rewritten in this project.

Fail-open by design: if git or the network is unavailable the script prints a
note and allows work rather than locking the user out.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import List, Optional

REPO = Path(os.environ.get("EIH_GUARD_REPO") or Path(__file__).resolve().parents[1]).resolve()
UPSTREAM = os.environ.get("EIH_GUARD_UPSTREAM", "origin/master")

# Files both laptops depend on (docs/WORK_PLAN.md §5). A change here on master
# must be pulled before either laptop edits anything.
SHARED_PREFIXES = (
    "core/",
    "configs/",
    "knowledge/schemas/",
    "knowledge/vector/",
    "evaluation/",
    "tests/conftest.py",
    "requirements.txt",
    "requirements-dev.txt",
    "pyproject.toml",
    "docker-compose.yml",
    ".env.example",
    ".gitignore",
    ".gitattributes",
    ".claude/",
    "scripts/git_sync_guard.py",
    "CLAUDE.md",
)


def git(*args: str, timeout: float = 20.0) -> Optional[str]:
    try:
        out = subprocess.run(
            ["git", *args], cwd=REPO, capture_output=True, text=True, timeout=timeout, check=True
        )
        return out.stdout.strip()
    except Exception:  # noqa: BLE001 - fail open
        return None


def missing_commits() -> List[str]:
    out = git("log", f"HEAD..{UPSTREAM}", "--no-merges", "--format=%h %an: %s")
    return [line for line in (out or "").splitlines() if line]


def must_pull_reasons() -> List[str]:
    reasons: List[str] = []
    tagged = git("log", f"HEAD..{UPSTREAM}", "--format=%h %s", "--grep=\\[must-pull\\]")
    reasons += [f"tagged [must-pull]: {line}" for line in (tagged or "").splitlines() if line]

    base = git("merge-base", "HEAD", UPSTREAM)
    if base:
        changed = git("diff", "--name-only", base, UPSTREAM) or ""
        shared = sorted({f for f in changed.splitlines() if f.startswith(SHARED_PREFIXES)})
        reasons += [f"shared file changed on master: {f}" for f in shared]
    return reasons


def unblock_command(branch: Optional[str]) -> str:
    if branch == "master":
        return "git checkout master; git pull"
    return f"git fetch; git merge origin/master   (you are on '{branch}'; never rebase)"


def session() -> None:
    fetched = git("fetch", "--quiet", "origin", timeout=30.0) is not None
    branch = git("rev-parse", "--abbrev-ref", "HEAD")
    dirty = git("status", "--porcelain", "--untracked-files=no")
    missing = missing_commits()
    reasons = must_pull_reasons()

    lines = [
        "[git sync guard] Repository: " + str(REPO),
        f"Branch: {branch}. Uncommitted tracked changes: {'yes' if dirty else 'no'}.",
        "Fetched from GitHub just now." if fetched else
        "WARNING: could not reach GitHub; the comparison below uses the last fetch.",
    ]
    message = None
    if not missing:
        lines.append(f"Up to date with {UPSTREAM}: nothing from the other laptop is missing.")
    else:
        lines.append(f"{len(missing)} commit(s) on {UPSTREAM} are NOT in this checkout:")
        lines += [f"  - {c}" for c in missing[:15]]
        if reasons:
            lines.append("MUST PULL BEFORE EDITING ANY CODE. Reasons:")
            lines += [f"  - {r}" for r in reasons[:15]]
            lines.append("Edits to this repo are blocked until you run: " + unblock_command(branch))
            message = ("⚠ PULL FIRST: the other laptop merged a must-pull change. Code edits are "
                       "blocked until you run: " + unblock_command(branch))
        else:
            lines.append("None of them is must-pull, but pull before starting new work: "
                         + unblock_command(branch))
            message = f"ℹ {len(missing)} new commit(s) on master from the other laptop. Pull before new work."
    lines.append("Follow the Session routine in CLAUDE.md: tell the user this status first.")

    payload = {"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": "\n".join(lines)}}
    if message:
        payload["systemMessage"] = message
    print(json.dumps(payload))


def merging_upstream() -> bool:
    """True while a merge that brings in the upstream tip is in progress.

    Resolving that merge's conflicts IS the sync this guard asks for, so edits
    must be allowed during it (found live: a PROGRESS-A.md conflict could not be
    resolved because HEAD did not yet contain the must-pull commits).
    """
    merge_head = git("rev-parse", "-q", "--verify", "MERGE_HEAD")
    if not merge_head:
        return False
    return git("merge-base", "--is-ancestor", UPSTREAM, merge_head) is not None


def pretool() -> None:
    try:
        data = json.load(sys.stdin)
    except Exception:  # noqa: BLE001
        return
    path = (data.get("tool_input") or {}).get("file_path") or ""
    try:
        Path(path).resolve().relative_to(REPO)
    except Exception:  # noqa: BLE001 - file outside this repo (memory, scratchpad): allow
        return
    if merging_upstream():
        return

    reasons = must_pull_reasons()
    if not reasons:
        return
    branch = git("rev-parse", "--abbrev-ref", "HEAD")
    reason = (
        "Blocked by the two-laptop git sync guard: origin/master has must-pull changes that "
        "this branch does not have (" + "; ".join(reasons[:5]) + "). Tell the user to pull "
        "first, then run: " + unblock_command(branch) + " — and re-run the tests."
    )
    print(json.dumps({"hookSpecificOutput": {
        "hookEventName": "PreToolUse",
        "permissionDecision": "deny",
        "permissionDecisionReason": reason,
    }}))


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "session"
    {"session": session, "pretool": pretool}.get(mode, session)()
