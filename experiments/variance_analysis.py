"""
Run-to-run variance and truncation check over 3-trial Mode Q runs (Steps 2c, 2e). Dev/val only.

Reads job-queue ledgers and reports, per system:
  * share of tasks whose 3 answers are identical, and mean distinct answers per task
  * within-task SD of output tokens and of lexical correctness F1, and the share of the
    total F1 variance that is within-task (trial-to-trial) rather than between tasks
  * agreement of the binary outcomes (supported, grounded success) across trials
  * truncation: trials that stopped at the output-token limit
  * a descriptive dev/val summary (means; NOT results for any claim: dev/val is for calibration)

    python -m experiments.variance_analysis --runs modeq-val-2c-2026-10-06,modeq-dev-2c-2026-10-06 \
        --run-id variance-2c-2026-10-06
"""

from __future__ import annotations

import argparse
import hashlib
import json
import statistics as st
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

REPO_ROOT = Path(__file__).resolve().parents[1]
QUEUE = REPO_ROOT / "experiments" / "results" / "queue" / "machine_A"
OUT_ROOT = REPO_ROOT / "experiments" / "results" / "variance"


def load(runs: List[str]) -> List[Dict[str, Any]]:
    out = []
    for run in runs:
        for line in (QUEUE / run / "results.jsonl").read_text(encoding="utf-8").splitlines():
            if line.strip():
                rec = json.loads(line)
                if rec.get("status") == "ok":
                    out.append({**rec["result"], "_run": run})
    return out


def _mean(xs):
    xs = [x for x in xs if x is not None]
    return sum(xs) / len(xs) if xs else None


def analyse(trials: List[Dict[str, Any]], max_output: int) -> Dict[str, Any]:
    by = defaultdict(lambda: defaultdict(list))
    for t in trials:
        by[t["system_id"]][t["task_id"]].append(t)
    res = {}
    for sid, tasks in sorted(by.items()):
        complete = {k: v for k, v in tasks.items() if len(v) >= 3}
        distinct = [len({hashlib.sha256(x["generated_answer"].encode("utf-8")).hexdigest() for x in v})
                    for v in complete.values()]
        tok_sd = [st.stdev([x["output_tokens"] for x in v]) for v in complete.values()]
        f1s = {k: [x["task_correctness"] for x in v if x["task_correctness"] is not None] for k, v in complete.items()}
        within = [st.pvariance(v) for v in f1s.values() if len(v) >= 2]
        allf1 = [x for v in f1s.values() for x in v]
        total = st.pvariance(allf1) if len(allf1) > 1 else None

        def agree(field):
            vals = [[x[field] for x in v] for v in complete.values()]
            vals = [v for v in vals if None not in v]
            return (sum(1 for v in vals if len(set(v)) == 1) / len(vals)) if vals else None

        flat = [x for v in tasks.values() for x in v]
        answered = [x for x in flat if not x["is_grounded_refusal"]]
        res[sid] = {
            "trials": len(flat), "tasks": len(tasks), "tasks_with_3_trials": len(complete),
            "tasks_identical_across_trials": sum(1 for d in distinct if d == 1),
            "mean_distinct_answers_per_task": _mean(distinct),
            "mean_within_task_sd_output_tokens": _mean(tok_sd),
            "within_task_share_of_f1_variance": (_mean(within) / total) if within and total else None,
            "agreement_answer_supported": agree("answer_supported"),
            "agreement_grounded_success": agree("grounded_success"),
            "truncated_trials": sum(1 for x in flat if x.get("output_truncated")),
            "trials_at_output_cap": sum(1 for x in flat if x["output_tokens"] >= max_output),
            "max_output_tokens_seen": max(x["output_tokens"] for x in flat),
            "summary_dev_val_descriptive": {
                "mean_correctness_f1": _mean(x["task_correctness"] for x in flat),
                "f1_at_or_above_task_threshold": sum(1 for x in flat if x["task_correctness"] is not None
                                                     and x["task_correctness"] >= x["quality_threshold"]),
                "refusal_rate": sum(1 for x in flat if x["is_grounded_refusal"]) / len(flat),
                "unsupported_rate_non_refusals": (sum(1 for x in answered if x["answer_supported"] is False)
                                                  / sum(1 for x in answered if x["answer_supported"] is not None))
                if any(x["answer_supported"] is not None for x in answered) else None,
                "grounded_success_rate": _mean([1.0 if x["grounded_success"] else 0.0 for x in flat
                                                if x["grounded_success"] is not None]),
                "gate_success_rate_secondary": _mean([1.0 if x["quality_constrained_success"] else 0.0 for x in flat
                                                      if x["quality_constrained_success"] is not None]),
                "mean_latency_s": _mean(x["latency_ms"] / 1000 for x in flat),
                "mean_output_tokens": _mean(x["output_tokens"] for x in flat),
                "mean_gpu_energy_j": _mean(x["gpu_energy_joules"] for x in flat),
                "mean_non_generation_gpu_j": _mean(x.get("retrieval_gpu_energy_joules") for x in flat),
                "model_loads": sum(x.get("model_loads") or 0 for x in flat),
                "max_gpu_temp_c": max((x.get("gpu_max_temp_c") or 0) for x in flat),
            },
        }
    return res


def main(argv=None) -> int:
    from core.inference import inference_config

    p = argparse.ArgumentParser()
    p.add_argument("--runs", required=True)
    p.add_argument("--run-id", required=True)
    p.add_argument("--machine", default="machine_A")
    args = p.parse_args(argv)
    runs = [r for r in args.runs.split(",") if r]
    trials = load(runs)
    if any(t["dataset_split"] == "test" for t in trials):
        raise SystemExit("test-split trials found: this analysis is for dev/val only")
    max_out = inference_config().max_output_tokens
    res = {"created_utc": datetime.now(timezone.utc).isoformat(), "runs": runs, "trials": len(trials),
           "max_output_tokens": max_out, "manifest_hashes": sorted({t["manifest_hash"] for t in trials}),
           "systems": analyse(trials, max_out)}
    out = OUT_ROOT / args.machine / args.run_id
    out.mkdir(parents=True, exist_ok=True)
    (out / "variance.json").write_text(json.dumps(res, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(res, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
