"""
Does a model reload or the output limit change a temperature-0 answer? (Step 2c; D16). Dev only.

On 2026-10-05 System A (no retrieval, identical 145-token prompt) answered dev task req-008 with
482 tokens in one job-queue run and 347 in the next. Same-session repeats are identical
(determinism_probe.py), so this probe varies what differed between those runs:

  warm        3 runs, model resident
  reloaded    3 runs, each after unloading the model (keep_alive 0) so it is loaded fresh
  limit_1024  2 runs with max output 1,024 instead of 2,048 (num_predict), model resident

    python -m experiments.determinism_reload_probe --run-id determinism-reload-2026-10-06
"""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import httpx

REPO_ROOT = Path(__file__).resolve().parents[1]
OUT_ROOT = REPO_ROOT / "experiments" / "results" / "determinism"


def main(argv=None) -> int:
    from core.config import settings
    from core.inference import inference_config
    from experiments.m5.runner import M5BenchmarkRunner
    from scripts.job_queue import load_split_tasks

    p = argparse.ArgumentParser()
    p.add_argument("--run-id", required=True)
    p.add_argument("--machine", default="machine_A")
    p.add_argument("--system", default="baseline_a")
    p.add_argument("--task", default="eih-phase1-req-008")
    args = p.parse_args(argv)
    task = {t.task_id: t for t in load_split_tasks("dev")}[args.task]
    runner = M5BenchmarkRunner()
    model = inference_config().fixed_model

    def unload() -> None:
        httpx.post("http://localhost:11434/api/generate", json={"model": model, "keep_alive": 0}, timeout=120)

    def run(tag: str) -> dict:
        r = runner._execute_system(system_id=args.system, task=task, llm_provider=runner.llm_provider)
        return {"tag": tag, "sha": hashlib.sha256(r.answer.encode("utf-8")).hexdigest()[:16],
                "output_tokens": r.output_tokens, "input_tokens": r.input_tokens,
                "cold_start": bool((r.metadata or {}).get("generation_cold_start"))}

    runs = []
    run("discard")  # make sure the model is resident
    runs += [run("warm") for _ in range(3)]
    for _ in range(3):
        unload()
        runs.append(run("reloaded"))
    original = settings.model.max_tokens
    try:
        settings.model.max_tokens = 1024
        runner._pipe_a = None  # rebuild with the new limit
        runs += [run("limit_1024") for _ in range(2)]
    finally:
        settings.model.max_tokens = original
    by_tag = {}
    for r in runs:
        by_tag.setdefault(r["tag"], []).append(r)
    res = {"created_utc": datetime.now(timezone.utc).isoformat(), "system": args.system, "task": args.task,
           "model": model, "runs": runs,
           "distinct_answers_by_condition": {k: len({r["sha"] for r in v}) for k, v in by_tag.items()},
           "distinct_answers_overall": len({r["sha"] for r in runs if r["tag"] != "discard"})}
    out = OUT_ROOT / args.machine / args.run_id
    out.mkdir(parents=True, exist_ok=True)
    (out / "probe.json").write_text(json.dumps(res, indent=2) + "\n", encoding="utf-8")
    for r in runs:
        print(r)
    print(res["distinct_answers_by_condition"], "overall", res["distinct_answers_overall"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
