"""
Effect of classifier errors on model routing (RQ4; Step 3 freeze note). Dev/val only, no GPU.

For each dev/val task, the TierRouter's starting model is computed twice: from the real
classifier's output (what System E + routing does) and from the benchmark's own labels
(complexity, criticality; security sensitivity as the classifier infers it, since the benchmark
labels it too coarsely to compare). The share of tasks where the starting tier differs is the routing
consequence of classification error. The classifier is not tuned further (decision 2026-10-06).

    python -m experiments.routing_effect --run-id routing-effect-2026-10-06
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
OUT_ROOT = REPO_ROOT / "experiments" / "results" / "routing_effect"


def main(argv=None) -> int:
    from benchmark.retrieval_labels import load_dev_val_tasks
    from intelligence.classifier import RuleBasedTaskClassifier
    from knowledge.schemas.tasks import EngTaskRequest
    from routing.registry import ModelRegistry
    from routing.tier_router import TierRouter

    p = argparse.ArgumentParser()
    p.add_argument("--run-id", required=True)
    args = p.parse_args(argv)
    tasks, split_of = load_dev_val_tasks()
    clf = RuleBasedTaskClassifier()
    router = TierRouter(ModelRegistry.from_yaml("configs/models.yaml"))
    rows = []
    for tid in sorted(tasks):
        t = tasks[tid]
        pred = clf.classify(EngTaskRequest(task_id=tid, query=t["query"], repository=t["repository"]))
        oracle = pred.model_copy(update={"complexity": t["complexity"], "criticality": t["criticality"]})
        rows.append({"task_id": tid, "split": split_of[tid],
                     "predicted": {"complexity": str(getattr(pred.complexity, "value", pred.complexity)),
                                   "criticality": str(getattr(pred.criticality, "value", pred.criticality))},
                     "label": {"complexity": t["complexity"], "criticality": t["criticality"]},
                     "model_from_classifier": router.select_model(pred),
                     "model_from_labels": router.select_model(oracle)})
    res = {"created_utc": datetime.now(timezone.utc).isoformat(), "tasks": len(rows)}
    for split in ("dev", "val"):
        rs = [r for r in rows if r["split"] == split]
        res[split] = {"tasks": len(rs), "same_start_tier": sum(r["model_from_classifier"] == r["model_from_labels"] for r in rs),
                      "pairs": dict(Counter(f"{r['model_from_labels']} -> {r['model_from_classifier']}" for r in rs))}
    res["rows"] = rows
    out = OUT_ROOT / "machine_A" / args.run_id
    out.mkdir(parents=True, exist_ok=True)
    (out / "routing_effect.json").write_text(json.dumps(res, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in res.items() if k != "rows"}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
