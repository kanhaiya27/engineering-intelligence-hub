"""Tests for scripts/job_queue.py — exactly-once ledger, resume, thermal rule, lock, test-split guard."""

from __future__ import annotations

import json
import os

import pytest

from scripts.job_queue import (
    GpuLock,
    JobQueue,
    ThermalGuard,
    build_plan,
    check_test_split_allowed,
)

SYSTEMS = ["baseline_a", "system_e"]
TASKS = ["t1", "t2", "t3"]


class Temps:
    """Scripted temperature sensor: returns the queued readings, then `rest`."""

    def __init__(self, readings=(), rest=50):
        self.readings, self.rest = list(readings), rest

    def __call__(self):
        return self.readings.pop(0) if self.readings else self.rest


def guard(temps=None):
    return ThermalGuard(read_temp=temps or Temps(), sleep=lambda s: None, poll_s=1.0)


def make_queue(tmp_path, execute, temps=None, plan=None):
    plan = plan or build_plan(SYSTEMS, TASKS, trials=2, seed=42)
    return JobQueue(tmp_path / "run1", {"split": "dev"}, plan, execute, guard(temps), log=lambda m: None)


def ok_executor(calls):
    def execute(unit):
        calls.append(unit["unit_id"])
        return {"answer": unit["unit_id"]}
    return execute


def test_plan_interleaves_systems_and_is_seeded():
    plan = build_plan(SYSTEMS, TASKS, trials=2, seed=42)
    assert len(plan) == 12 and len({u["unit_id"] for u in plan}) == 12
    assert plan == build_plan(SYSTEMS, TASKS, trials=2, seed=42)
    assert plan != build_plan(SYSTEMS, TASKS, trials=2, seed=7)
    first_round = [u["system_id"] for u in plan[:6]]
    assert first_round != sorted(first_round), "systems must not run in fixed blocks"
    assert all(u["trial_index"] == 0 for u in plan[:6]), "every pair once per round"


def test_every_unit_runs_exactly_once(tmp_path):
    calls = []
    q = make_queue(tmp_path, ok_executor(calls))
    status = q.run()
    assert sorted(calls) == sorted(u["unit_id"] for u in q.plan)
    assert status == {"run_id": "run1", "units": 12, "finished": 12, "pending": 0,
                      "by_status": {"ok": 12}, "discarded_over_temp": 0}


def test_resume_after_crash_skips_finished_units_without_duplicates(tmp_path):
    calls = []

    def crashing(unit):
        if len(calls) == 5:
            raise KeyboardInterrupt  # the process dies mid-run
        calls.append(unit["unit_id"])
        return {}

    q = make_queue(tmp_path, crashing)
    with pytest.raises(KeyboardInterrupt):
        q.run()
    assert q.status()["finished"] == 5

    calls2 = []
    q2 = make_queue(tmp_path, ok_executor(calls2))
    q2.run()
    assert len(calls2) == 7 and not set(calls2) & set(calls)
    rows = [json.loads(line) for line in (tmp_path / "run1" / "results.jsonl").read_text().splitlines()]
    assert len(rows) == 12 and len({r["unit_id"] for r in rows}) == 12


def test_truncated_last_line_from_a_crash_is_rerun(tmp_path):
    q = make_queue(tmp_path, ok_executor([]))
    q.run()
    path = tmp_path / "run1" / "results.jsonl"
    lines = path.read_text().splitlines()
    path.write_text("\n".join(lines[:-1]) + "\n" + lines[-1][:20])  # half-written final row
    calls = []
    make_queue(tmp_path, ok_executor(calls)).run()
    assert calls == [json.loads(lines[-1])["unit_id"]]
    assert make_queue(tmp_path, ok_executor([])).status()["finished"] == 12, "re-run row must not be lost"


def test_errors_are_recorded_not_dropped_and_can_be_retried(tmp_path):
    def flaky(unit):
        if unit["task_id"] == "t2":
            raise ValueError("retrieval returned nothing")
        return {}

    q = make_queue(tmp_path, flaky)
    status = q.run()
    assert status["by_status"] == {"ok": 8, "error": 4} and status["pending"] == 0
    err = next(r for r in q.latest().values() if r["status"] == "error")
    assert err["error"] == "ValueError: retrieval returned nothing" and err["result"] is None

    calls = []
    q2 = make_queue(tmp_path, ok_executor(calls))
    assert q2.run()["by_status"] == {"ok": 8, "error": 4}, "errors are not re-run by default"
    assert calls == []
    assert q2.run(retry_errors=True)["by_status"] == {"ok": 12}
    assert len(calls) == 4 and all("|t2|" in c for c in calls)


def test_over_temperature_unit_is_discarded_cooled_and_repeated(tmp_path):
    plan = build_plan(["baseline_a"], ["t1"], trials=1, seed=1)
    # readings: before-check 60, start 60, end 93 (too hot) -> cool_down: 93, 80, 64 -> retry: 60, 60, end 70
    temps = Temps([60, 60, 93, 93, 80, 64, 60, 60, 70])
    calls = []
    q = make_queue(tmp_path, ok_executor(calls), temps=temps, plan=plan)
    status = q.run()
    assert calls == ["baseline_a|t1|0", "baseline_a|t1|0"]
    assert status["by_status"] == {"ok": 1} and status["discarded_over_temp"] == 1
    row = q.latest()["baseline_a|t1|0"]
    assert row["thermal_attempt"] == 1 and row["temp_end_c"] == 70
    assert row["cooldowns"][0]["from_c"] == 93 and row["cooldowns"][0]["to_c"] == 64
    discarded = json.loads((tmp_path / "run1" / "discarded.jsonl").read_text().splitlines()[0])
    assert discarded["temp_end_c"] == 93


def test_starts_with_a_cooldown_when_already_too_hot(tmp_path):
    plan = build_plan(["baseline_a"], ["t1"], trials=1, seed=1)
    q = make_queue(tmp_path, ok_executor([]), temps=Temps([95, 95, 70, 60, 61, 62]), plan=plan)
    q.run()
    row = q.latest()["baseline_a|t1|0"]
    assert row["cooldowns"][0]["to_c"] == 60 and row["temp_start_c"] == 61


def test_unit_that_stays_too_hot_is_marked_thermal_fail(tmp_path):
    plan = build_plan(["baseline_a"], ["t1"], trials=1, seed=1)
    q = make_queue(tmp_path, ok_executor([]), temps=Temps(rest=95), plan=plan)
    q.thermal.max_wait_s = 3
    status = q.run()
    assert status["by_status"] == {"thermal_fail": 1} and status["discarded_over_temp"] == 3


def test_same_run_id_with_a_different_plan_is_refused(tmp_path):
    make_queue(tmp_path, ok_executor([]))
    with pytest.raises(RuntimeError, match="different plan"):
        make_queue(tmp_path, ok_executor([]), plan=build_plan(SYSTEMS, TASKS, trials=3, seed=42))


def test_lock_blocks_a_second_run_and_takes_over_a_stale_lock(tmp_path):
    lock = tmp_path / "gpu.lock"
    with GpuLock(lock, "first"):
        with pytest.raises(RuntimeError, match="busy"):
            with GpuLock(lock, "second"):
                pass
    assert not lock.exists()
    lock.write_text(json.dumps({"pid": 999_999_999, "run_id": "dead"}))  # process long gone
    with GpuLock(lock, "third"):
        assert json.loads(lock.read_text())["pid"] == os.getpid()


def test_test_split_needs_final_flag_and_runs_only_once(tmp_path):
    check_test_split_allowed("dev", False, tmp_path, "r")  # other splits are unrestricted
    with pytest.raises(RuntimeError, match="--final-test"):
        check_test_split_allowed("test", False, tmp_path, "final")
    check_test_split_allowed("test", True, tmp_path, "final")
    run_dir = tmp_path / "machine_A" / "final"
    run_dir.mkdir(parents=True)
    (run_dir / "run.json").write_text(json.dumps({"config": {"split": "test"}}))
    check_test_split_allowed("test", True, tmp_path, "final")  # resuming the same run is allowed
    with pytest.raises(RuntimeError, match="only once"):
        check_test_split_allowed("test", True, tmp_path, "another")
