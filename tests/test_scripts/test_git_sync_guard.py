"""
Tests for scripts/git_sync_guard.py against throwaway git repositories:
a bare "GitHub" remote, this laptop's clone, and the other laptop's clone.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

GUARD = Path(__file__).resolve().parents[2] / "scripts" / "git_sync_guard.py"


def git(cwd: Path, *args: str) -> str:
    env = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t",
           "GIT_COMMITTER_EMAIL": "t@t"}
    return subprocess.run(["git", *args], cwd=cwd, env=env, capture_output=True, text=True, check=True).stdout


def commit(repo: Path, rel: str, text: str, msg: str) -> None:
    f = repo / rel
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(text, encoding="utf-8")
    git(repo, "add", rel)
    git(repo, "commit", "-q", "-m", msg)


@pytest.fixture
def laptops(tmp_path):
    remote = tmp_path / "github.git"
    git(tmp_path, "init", "-q", "--bare", "-b", "master", str(remote))
    a, b = tmp_path / "laptop_a", tmp_path / "laptop_b"
    git(tmp_path, "clone", "-q", str(remote), str(a))
    git(a, "checkout", "-q", "-b", "master")
    commit(a, "README.md", "hi\n", "init")
    git(a, "push", "-q", "-u", "origin", "master")
    git(tmp_path, "clone", "-q", str(remote), str(b))
    return a, b


def run_guard(repo: Path, mode: str, payload: dict) -> str:
    env = {**os.environ, "EIH_GUARD_REPO": str(repo), "PYTHONIOENCODING": "utf-8"}
    env.pop("EIH_GUARD_UPSTREAM", None)
    return subprocess.run([sys.executable, str(GUARD), mode], input=json.dumps(payload), env=env,
                          capture_output=True, text=True, timeout=60).stdout


def edit_payload(repo: Path, rel: str) -> dict:
    return {"tool_name": "Edit", "tool_input": {"file_path": str(repo / rel)}}


def decision(out: str) -> str:
    return "allow" if not out.strip() else json.loads(out)["hookSpecificOutput"]["permissionDecision"]


def test_up_to_date_allows_and_reports_clean(laptops):
    a, _ = laptops
    assert decision(run_guard(a, "pretool", edit_payload(a, "retrieval/x.py"))) == "allow"
    ctx = json.loads(run_guard(a, "session", {}))
    assert "Up to date" in ctx["hookSpecificOutput"]["additionalContext"]
    assert "systemMessage" not in ctx


def test_tagged_must_pull_blocks_until_pulled(laptops):
    a, b = laptops
    commit(b, "benchmark/tasks.json", "[]\n", "feat(benchmark): new schema field [must-pull]")
    git(b, "push", "-q", "origin", "master")

    session = json.loads(run_guard(a, "session", {}))          # fetches
    assert "PULL FIRST" in session["systemMessage"]
    assert decision(run_guard(a, "pretool", edit_payload(a, "retrieval/x.py"))) == "deny"

    git(a, "pull", "-q")
    assert decision(run_guard(a, "pretool", edit_payload(a, "retrieval/x.py"))) == "allow"


def test_untagged_shared_file_change_also_blocks(laptops):
    a, b = laptops
    commit(b, "core/config.py", "X = 1\n", "fix(config): forgot the tag")
    git(b, "push", "-q", "origin", "master")
    run_guard(a, "session", {})
    out = run_guard(a, "pretool", edit_payload(a, "generation/y.py"))
    assert decision(out) == "deny"
    assert "core/config.py" in json.loads(out)["hookSpecificOutput"]["permissionDecisionReason"]


def test_owned_folder_change_warns_but_does_not_block(laptops):
    a, b = laptops
    commit(b, "benchmark/notes.md", "n\n", "docs(benchmark): notes")
    git(b, "push", "-q", "origin", "master")
    session = json.loads(run_guard(a, "session", {}))
    assert "new commit" in session["systemMessage"]
    assert decision(run_guard(a, "pretool", edit_payload(a, "retrieval/x.py"))) == "allow"


def test_feature_branch_unblocked_by_merging_master(laptops):
    a, b = laptops
    git(a, "checkout", "-q", "-b", "feat/x")
    commit(b, "docker-compose.yml", "services: {}\n", "fix(compose): healthcheck [must-pull]")
    git(b, "push", "-q", "origin", "master")
    run_guard(a, "session", {})
    out = run_guard(a, "pretool", edit_payload(a, "retrieval/x.py"))
    assert decision(out) == "deny"
    assert "git merge origin/master" in json.loads(out)["hookSpecificOutput"]["permissionDecisionReason"]
    git(a, "merge", "-q", "--no-edit", "origin/master")
    assert decision(run_guard(a, "pretool", edit_payload(a, "retrieval/x.py"))) == "allow"


def test_edits_allowed_while_resolving_a_merge_of_master(laptops):
    a, b = laptops
    commit(a, "PROGRESS-A.md", "mine\n", "docs: my entry")
    commit(b, "PROGRESS-A.md", "theirs\n", "docs: their entry [must-pull]")
    git(b, "push", "-q", "origin", "master")
    run_guard(a, "session", {})
    assert decision(run_guard(a, "pretool", edit_payload(a, "PROGRESS-A.md"))) == "deny"
    with pytest.raises(subprocess.CalledProcessError):      # conflicting merge stops half-way
        git(a, "merge", "--no-edit", "origin/master")
    assert decision(run_guard(a, "pretool", edit_payload(a, "PROGRESS-A.md"))) == "allow"


def test_files_outside_the_repo_are_never_blocked(laptops, tmp_path):
    a, b = laptops
    commit(b, "core/config.py", "X = 2\n", "fix: shared [must-pull]")
    git(b, "push", "-q", "origin", "master")
    run_guard(a, "session", {})
    outside = {"tool_name": "Write", "tool_input": {"file_path": str(tmp_path / "notes" / "memo.md")}}
    assert decision(run_guard(a, "pretool", outside)) == "allow"
