"""
Engineering Intelligence Hub — GPU job queue for long measured runs
===================================================================
Runs benchmark work as small units — one (system, task, trial) each — on the
single laptop GPU, so a run of hundreds of calls survives crashes, heat and
mistakes without corrupting its results:

  * exactly once   every finished unit is appended (and fsynced) to
                   results.jsonl; re-running the same --run-id resumes and
                   skips finished units, so a crash never duplicates trials
  * nothing lost   a unit that raises is recorded with its error (status
                   "error"), never silently dropped; --retry-errors re-runs them
  * fair order     units are interleaved and shuffled per trial round (seeded),
                   so no system always runs first on a cool GPU or last on a hot one
  * thermal rule   (owner, 2026-10-05) work up to 90 °C; a unit that ends above it
                   is discarded (kept in discarded.jsonl), the GPU cools to 65 °C,
                   and the unit is repeated
  * one GPU user   a lock file stops two queue runs from sharing the GPU
  * held-out test  the test split runs only with --final-test, and only once

Temperature is read between units only (one NVML read), never polled during a
measurement: polling perturbs the energy counter on this driver.

Usage (PowerShell, repo root):
  python -m scripts.job_queue run --run-id dev-r1 --split dev --trials 3
  python -m scripts.job_queue run --run-id dev-r1 --split dev --trials 3   # resume
  python -m scripts.job_queue status --run-id dev-r1

Output: experiments/results/queue/<machine>/<run-id>/
  run.json (provenance + config), plan.jsonl, results.jsonl, discarded.jsonl,
  summary.json (per system/task aggregates, written when every unit is done)
"""

from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import json
import os
import random
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional

from core.config import PROJECT_ROOT, settings

QUEUE_ROOT = PROJECT_ROOT / "experiments" / "results" / "queue"
LOCK_PATH = PROJECT_ROOT / "experiments" / "results" / ".gpu_queue.lock"
ALL_SYSTEMS = ["baseline_a", "baseline_b", "system_c", "system_d", "system_e"]
MAX_TEMP_C = 90
RESUME_TEMP_C = 65
MAX_THERMAL_RETRIES = 2


def _now() -> str:
    return _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds")


def machine_dir() -> str:
    mid = (settings.machine_id or "").strip().lower()
    return {"laptop-a": "machine_A", "laptop-b": "machine_B"}.get(mid, mid or "machine_unknown")


# --------------------------------------------------------------------------- plan
def build_plan(systems: List[str], task_ids: List[str], trials: int, seed: int) -> List[Dict[str, Any]]:
    """Trial-major rounds; inside each round every (system, task) pair once, shuffled."""
    plan = []
    for trial in range(trials):
        pairs = [(s, t) for s in systems for t in task_ids]
        random.Random(seed + trial).shuffle(pairs)
        for s, t in pairs:
            plan.append({"unit_id": f"{s}|{t}|{trial}", "system_id": s, "task_id": t, "trial_index": trial})
    return plan


def plan_hash(plan: List[Dict[str, Any]]) -> str:
    return hashlib.sha256(json.dumps(plan, sort_keys=True).encode()).hexdigest()[:16]


# --------------------------------------------------------------------------- lock
class GpuLock:
    """Exclusive lock file; a lock left by a dead process is taken over."""

    def __init__(self, path: Path = LOCK_PATH, run_id: str = "") -> None:
        self.path, self.run_id = path, run_id

    @staticmethod
    def _alive(pid: int) -> bool:
        import psutil

        return psutil.pid_exists(pid)

    def __enter__(self) -> "GpuLock":
        self.path.parent.mkdir(parents=True, exist_ok=True)
        for _ in range(2):
            try:
                fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            except FileExistsError:
                try:
                    held = json.loads(self.path.read_text(encoding="utf-8"))
                except (OSError, ValueError):
                    held = {}
                if held.get("pid") and self._alive(int(held["pid"])):
                    raise RuntimeError(f"GPU queue is busy: run '{held.get('run_id')}' (pid {held['pid']}) "
                                       f"holds {self.path}.")
                self.path.unlink(missing_ok=True)  # stale: its process is gone
                continue
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump({"pid": os.getpid(), "run_id": self.run_id, "since": _now()}, f)
            return self
        raise RuntimeError(f"Could not take the GPU queue lock {self.path}")

    def __exit__(self, *exc) -> None:
        self.path.unlink(missing_ok=True)


# --------------------------------------------------------------------------- thermal
@dataclass
class ThermalGuard:
    read_temp: Callable[[], Optional[int]]
    sleep: Callable[[float], None] = time.sleep
    max_c: int = MAX_TEMP_C
    resume_c: int = RESUME_TEMP_C
    poll_s: float = 5.0
    max_wait_s: float = 1800.0

    def too_hot(self, temp: Optional[int]) -> bool:
        return temp is not None and temp > self.max_c

    def cool_down(self) -> Dict[str, Any]:
        start = temp = self.read_temp()
        waited = 0.0
        while temp is not None and temp > self.resume_c and waited < self.max_wait_s:
            self.sleep(self.poll_s)
            waited += self.poll_s
            temp = self.read_temp()
        return {"from_c": start, "to_c": temp, "waited_s": waited, "at": _now()}


def nvml_temp() -> Optional[int]:
    try:
        import pynvml  # type: ignore[import]

        pynvml.nvmlInit()
        return int(pynvml.nvmlDeviceGetTemperature(pynvml.nvmlDeviceGetHandleByIndex(0),
                                                   pynvml.NVML_TEMPERATURE_GPU))
    except Exception:  # noqa: BLE001 - no NVML: the thermal rule cannot apply, recorded as None
        return None


# --------------------------------------------------------------------------- queue
def _append(path: Path, row: Dict[str, Any]) -> None:
    # A crash mid-write can leave a final line without "\n"; start on a fresh line
    # so the new row is not glued onto (and lost with) the broken one.
    broken_tail = False
    if path.exists() and path.stat().st_size:
        with open(path, "rb") as f:
            f.seek(-1, os.SEEK_END)
            broken_tail = f.read(1) != b"\n"
    with open(path, "a", encoding="utf-8") as f:
        f.write(("\n" if broken_tail else "") + json.dumps(row, default=str) + "\n")
        f.flush()
        os.fsync(f.fileno())


def _read_jsonl(path: Path) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            try:
                rows.append(json.loads(line))
            except ValueError:  # a line cut off by a crash mid-write: that unit simply re-runs
                pass
    return rows


class JobQueue:
    """Plan + ledger for one run directory. `execute(unit)` returns a JSON-able result dict."""

    def __init__(self, run_dir: Path, config: Dict[str, Any], plan: List[Dict[str, Any]],
                 execute: Callable[[Dict[str, Any]], Dict[str, Any]], thermal: ThermalGuard,
                 provenance: Optional[Callable[[], Dict[str, Any]]] = None,
                 log: Callable[[str], None] = print) -> None:
        self.run_dir, self.config, self.plan = run_dir, config, plan
        self.execute, self.thermal, self.log = execute, thermal, log
        self.results_path = run_dir / "results.jsonl"
        self.discarded_path = run_dir / "discarded.jsonl"
        self._init_run(provenance)

    def _init_run(self, provenance: Optional[Callable[[], Dict[str, Any]]]) -> None:
        self.run_dir.mkdir(parents=True, exist_ok=True)
        run_json = self.run_dir / "run.json"
        h = plan_hash(self.plan)
        if run_json.exists():
            existing = json.loads(run_json.read_text(encoding="utf-8"))
            if existing.get("plan_hash") != h:
                raise RuntimeError(f"Run '{self.run_dir.name}' exists with a different plan "
                                   f"({existing.get('plan_hash')} != {h}). Use a new --run-id.")
            return
        run_json.write_text(json.dumps({
            "study": "job_queue_run", "run_id": self.run_dir.name, "created_utc": _now(),
            "plan_hash": h, "n_units": len(self.plan), "config": self.config,
            "provenance": provenance() if provenance else None,
            "thermal_rule": {"max_temp_c": self.thermal.max_c, "resume_temp_c": self.thermal.resume_c,
                             "max_retries": MAX_THERMAL_RETRIES},
        }, indent=2, default=str), encoding="utf-8")
        with open(self.run_dir / "plan.jsonl", "w", encoding="utf-8") as f:
            for u in self.plan:
                f.write(json.dumps(u) + "\n")

    def latest(self) -> Dict[str, Dict[str, Any]]:
        """Latest ledger row per unit (a retried error is superseded by its re-run)."""
        out: Dict[str, Dict[str, Any]] = {}
        for row in _read_jsonl(self.results_path):
            out[row["unit_id"]] = row
        return out

    def pending(self, retry_errors: bool = False) -> List[Dict[str, Any]]:
        done = self.latest()
        return [u for u in self.plan if u["unit_id"] not in done
                or (retry_errors and done[u["unit_id"]]["status"] != "ok")]

    def _run_unit(self, unit: Dict[str, Any]) -> Dict[str, Any]:
        cooldowns = []
        for attempt in range(1 + MAX_THERMAL_RETRIES):
            if self.thermal.too_hot(self.thermal.read_temp()):
                cooldowns.append(self.thermal.cool_down())
            temp_start = self.thermal.read_temp()
            started, t0 = _now(), time.perf_counter()
            try:
                result, error = self.execute(unit), None
            except Exception as exc:  # noqa: BLE001 - recorded, never dropped
                result, error = None, f"{type(exc).__name__}: {exc}"
            row = {**unit, "status": "ok" if error is None else "error", "error": error, "result": result,
                   "started_utc": started, "wall_s": round(time.perf_counter() - t0, 3),
                   "temp_start_c": temp_start, "temp_end_c": self.thermal.read_temp(),
                   "thermal_attempt": attempt, "cooldowns": cooldowns}
            if not self.thermal.too_hot(row["temp_end_c"]):
                return row
            _append(self.discarded_path, {**row, "discarded_reason": f"temp_end_c > {self.thermal.max_c}"})
            self.log(f"  {unit['unit_id']}: ended at {row['temp_end_c']} °C > {self.thermal.max_c}; "
                     f"discarded, cooling down")
            cooldowns.append(self.thermal.cool_down())
        row["status"] = "thermal_fail"
        return row

    def run(self, retry_errors: bool = False) -> Dict[str, Any]:
        todo = self.pending(retry_errors)
        self.log(f"run '{self.run_dir.name}': {len(self.plan)} units, {len(todo)} to do")
        for i, unit in enumerate(todo, 1):
            row = self._run_unit(unit)
            _append(self.results_path, row)
            self.log(f"  [{i}/{len(todo)}] {unit['unit_id']}: {row['status']} {row['wall_s']:.1f}s "
                     f"{row['temp_start_c']}->{row['temp_end_c']} °C" + (f" {row['error']}" if row["error"] else ""))
        return self.status()

    def status(self) -> Dict[str, Any]:
        done = self.latest()
        counts: Dict[str, int] = {}
        for row in done.values():
            counts[row["status"]] = counts.get(row["status"], 0) + 1
        return {"run_id": self.run_dir.name, "units": len(self.plan), "finished": len(done),
                "pending": len(self.plan) - len(done), "by_status": counts,
                "discarded_over_temp": len(_read_jsonl(self.discarded_path))}


# --------------------------------------------------------------------------- held-out test guard
def check_test_split_allowed(split: str, final_test: bool, queue_root: Path, run_id: str) -> None:
    if split != "test":
        return
    if not final_test:
        raise RuntimeError("The held-out test split runs once, at the end, only with --final-test "
                           "(CLAUDE.md rule 3).")
    for run_json in queue_root.glob("*/*/run.json"):
        cfg = json.loads(run_json.read_text(encoding="utf-8")).get("config", {})
        if cfg.get("split") == "test" and run_json.parent.name != run_id:
            raise RuntimeError(f"The test split already has a run ({run_json.parent}); it runs only once. "
                               "Resume that run instead.")


# --------------------------------------------------------------------------- M5 binding
def m5_executor(provider_name: Optional[str], manifest_path: Optional[str], split: str):
    """Units execute through the existing M5 runner: pipeline per system, then trial evaluation."""
    from experiments.m5.manifest import ExperimentManifest
    from experiments.m5.runner import M5BenchmarkRunner

    manifest = None
    if manifest_path:
        manifest = ExperimentManifest(**json.loads(Path(manifest_path).read_text(encoding="utf-8")))
    runner = M5BenchmarkRunner(manifest=manifest, provider_name=provider_name)
    # A manifest that differs from what the pipelines actually run with would
    # certify settings that never ran: refuse it (mock runs are tests, not results).
    from experiments.m5.manifest import runtime_mismatches

    mismatches = runtime_mismatches(runner.manifest)
    if mismatches and (provider_name or "").lower() != "mock":
        raise RuntimeError(f"Manifest does not match the runtime settings: {mismatches}")
    tasks = {t.task_id: t for t in load_split_tasks(split)}

    def execute(unit: Dict[str, Any]) -> Dict[str, Any]:
        task = tasks[unit["task_id"]]
        resp = runner._execute_system(system_id=unit["system_id"], task=task, llm_provider=runner.llm_provider)
        trial = runner._evaluate_trial(system_id=unit["system_id"], task=task, response=resp,
                                       trial_index=unit["trial_index"], split_name=split)
        return json.loads(trial.model_dump_json())

    return execute, runner


def load_split_tasks(split: str) -> List[Any]:
    from benchmark.dataset import BenchmarkDataset
    from experiments.m5.splits import BENCHMARK_TASKS_PATH, load_or_create_splits

    ids = set(load_or_create_splits()["splits"].get(split, []))
    return [t for t in BenchmarkDataset.load_from_json(BENCHMARK_TASKS_PATH).tasks if t.task_id in ids]


def write_m5_summary(queue: JobQueue) -> Optional[Path]:
    """Per system/task aggregates over the ok units, once nothing is pending."""
    from experiments.m5.metrics import TrialResult, compute_trial_aggregates

    if queue.status()["pending"]:
        return None
    groups: Dict[str, Dict[str, List[Any]]] = {}
    for row in queue.latest().values():
        if row["status"] == "ok":
            groups.setdefault(row["system_id"], {}).setdefault(row["task_id"], []).append(TrialResult(**row["result"]))
    summary = {
        "study": "job_queue_m5_summary", "run_id": queue.run_dir.name, "written_utc": _now(),
        "provenance": json.loads((queue.run_dir / "run.json").read_text(encoding="utf-8")).get("provenance"),
        "results": {"status": queue.status(),
                    "aggregations": {s: [compute_trial_aggregates(v).model_dump() for v in by_task.values()]
                                     for s, by_task in groups.items()}},
    }
    path = queue.run_dir / "summary.json"
    path.write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
    return path


def main(argv: Optional[Iterable[str]] = None) -> None:
    ap = argparse.ArgumentParser(description="GPU job queue for measured benchmark runs")
    sub = ap.add_subparsers(dest="cmd", required=True)
    run = sub.add_parser("run", help="start or resume a run")
    run.add_argument("--run-id", required=True)
    run.add_argument("--split", required=True, choices=["dev", "val", "test"])
    run.add_argument("--systems", default=",".join(ALL_SYSTEMS))
    run.add_argument("--trials", type=int, default=3)
    run.add_argument("--max-tasks", type=int, default=None, help="first N tasks of the split (smoke runs)")
    run.add_argument("--seed", type=int, default=42)
    run.add_argument("--manifest", default=None)
    run.add_argument("--provider", default=None, help="ollama (default) | mock (tests only, never results)")
    run.add_argument("--retry-errors", action="store_true")
    run.add_argument("--final-test", action="store_true", help="required for the one held-out test run")
    st = sub.add_parser("status", help="show progress of a run")
    st.add_argument("--run-id", required=True)
    for p in (run, st):
        p.add_argument("--root", default=str(QUEUE_ROOT), help="queue root (smoke runs: a scratch dir)")
    args = ap.parse_args(list(argv) if argv is not None else None)

    root = Path(args.root)
    run_dir = root / machine_dir() / args.run_id
    if args.cmd == "status":
        rows = _read_jsonl(run_dir / "results.jsonl")
        plan = _read_jsonl(run_dir / "plan.jsonl")
        latest = {r["unit_id"]: r for r in rows}
        counts: Dict[str, int] = {}
        for r in latest.values():
            counts[r["status"]] = counts.get(r["status"], 0) + 1
        print(json.dumps({"run_id": args.run_id, "units": len(plan), "finished": len(latest),
                          "pending": len(plan) - len(latest), "by_status": counts,
                          "discarded_over_temp": len(_read_jsonl(run_dir / "discarded.jsonl"))}, indent=2))
        return

    check_test_split_allowed(args.split, args.final_test, QUEUE_ROOT, args.run_id)
    if root != QUEUE_ROOT:
        check_test_split_allowed(args.split, args.final_test, root, args.run_id)
    systems = [s.strip() for s in args.systems.split(",") if s.strip()]
    unknown = set(systems) - set(ALL_SYSTEMS)
    if unknown:
        raise SystemExit(f"Unknown systems: {sorted(unknown)}; use {ALL_SYSTEMS}")
    task_ids = [t.task_id for t in load_split_tasks(args.split)]
    if args.max_tasks:
        task_ids = task_ids[:args.max_tasks]
    plan = build_plan(systems, task_ids, args.trials, args.seed)

    from experiments.provenance import collect_provenance

    with GpuLock(run_id=args.run_id):
        execute, runner = m5_executor(args.provider, args.manifest, args.split)
        config = {"split": args.split, "systems": systems, "trials": args.trials, "seed": args.seed,
                  "max_tasks": args.max_tasks, "task_ids": task_ids, "manifest": args.manifest,
                  "manifest_hash": runner.manifest.compute_hash(),
                  "frozen_variables": runner.manifest.frozen_variables.model_dump(),
                  "provider": args.provider or settings.model.default_provider}
        queue = JobQueue(run_dir, config, plan, execute, ThermalGuard(read_temp=nvml_temp),
                         provenance=collect_provenance, log=lambda m: print(m, flush=True))
        status = queue.run(retry_errors=args.retry_errors)
        summary = write_m5_summary(queue)
    print(json.dumps(status, indent=2))
    print(f"summary: {summary}" if summary else "summary not written: units still pending")


if __name__ == "__main__":
    main()
