"""
Run-to-run determinism probe (Step 2c; WORK_PLAN D16). Dev tasks only.

At temperature 0 and seed 42, System C's answer to dev task req-010 was 778 tokens in one run
and 292 in another. This probe runs the SAME system/task several times in two orders:

  back_to_back   the same request repeated (Ollama's prompt cache holds this prompt)
  interleaved    alternating with a different dev task (the cache holds a different prompt)

and records, per run, the sha256 of the answer, the token counts and the retrieved chunk ids.
Retrieval is deterministic or not independently of generation, so both are compared.

    python -m experiments.determinism_probe --run-id determinism-2026-10-06 --repeats 5
"""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

REPO_ROOT = Path(__file__).resolve().parents[1]
OUT_ROOT = REPO_ROOT / "experiments" / "results" / "determinism"


def _summary(runs: List[Dict[str, Any]]) -> Dict[str, Any]:
    return {"runs": len(runs), "distinct_answers": len({r["answer_sha"] for r in runs}),
            "distinct_retrievals": len({r["retrieval_sha"] for r in runs}),
            "output_tokens": [r["output_tokens"] for r in runs],
            "answer_counts": dict(Counter(r["answer_sha"][:12] for r in runs))}


def main(argv=None) -> int:
    from experiments.m5.runner import M5BenchmarkRunner
    from scripts.job_queue import load_split_tasks

    p = argparse.ArgumentParser()
    p.add_argument("--run-id", required=True)
    p.add_argument("--machine", default="machine_A")
    p.add_argument("--system", default="system_c")
    p.add_argument("--task", default="eih-phase1-req-010")
    p.add_argument("--other-task", default="eih-phase1-req-008")
    p.add_argument("--repeats", type=int, default=5)
    args = p.parse_args(argv)

    tasks = {t.task_id: t for t in load_split_tasks("dev")}
    target, other = tasks[args.task], tasks[args.other_task]  # KeyError if not dev: test tasks never load
    runner = M5BenchmarkRunner()
    runner.warm_up([args.system])

    def run(task) -> Dict[str, Any]:
        resp = runner._execute_system(system_id=args.system, task=task, llm_provider=runner.llm_provider)
        ids = [c.chunk_id for c in (resp.retrieval.chunks if resp.retrieval else [])]
        return {"task_id": task.task_id, "answer_sha": hashlib.sha256(resp.answer.encode("utf-8")).hexdigest(),
                "retrieval_sha": hashlib.sha256("|".join(ids).encode("utf-8")).hexdigest(),
                "output_tokens": resp.output_tokens, "input_tokens": resp.input_tokens,
                "latency_ms": resp.latency_ms, "answer": resp.answer}

    run(target)  # untimed: loads the model and fills the cache once
    back = [run(target) for _ in range(args.repeats)]
    inter = []
    for _ in range(args.repeats):
        run(other)
        inter.append(run(target))
    res = {"created_utc": datetime.now(timezone.utc).isoformat(), "system": args.system, "task": args.task,
           "other_task": args.other_task, "options": runner.llm_provider._options.__self__.model_options
           if hasattr(runner.llm_provider, "model_options") else None,
           "back_to_back": _summary(back), "interleaved": _summary(inter),
           "all_runs_identical": len({r["answer_sha"] for r in back + inter}) == 1,
           "runs": {"back_to_back": back, "interleaved": inter}}
    out = OUT_ROOT / args.machine / args.run_id
    out.mkdir(parents=True, exist_ok=True)
    (out / "probe.json").write_text(json.dumps(res, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: res[k] for k in ("back_to_back", "interleaved", "all_runs_identical")}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
