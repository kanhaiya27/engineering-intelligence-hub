"""
Task-classifier accuracy against the benchmark's labels, dev and val only (Step 2a).

For each field (SDLC stage, task type, complexity, criticality): accuracy per split and a
confusion matrix (rows = benchmark label, columns = classifier output). Rules are improved on
DEV only; VAL is the untouched check. The benchmark's own labels are pilot labels that reviewers
are still checking (`labels_fit`), so agreement measures consistency with them, not ground truth.

    python -m experiments.classifier_eval --run-id classifier-before-2026-10-06
"""

from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

REPO_ROOT = Path(__file__).resolve().parents[1]
OUT_ROOT = REPO_ROOT / "experiments" / "results" / "classifier"
FIELDS = ("sdlc_stage", "task_type", "complexity", "criticality")


def evaluate() -> Dict[str, Any]:
    from benchmark.retrieval_labels import load_dev_val_tasks
    from intelligence.classifier import RuleBasedTaskClassifier
    from knowledge.schemas.tasks import EngTaskRequest

    tasks, split_of = load_dev_val_tasks()
    clf = RuleBasedTaskClassifier()
    per_task, conf = {}, {s: {f: defaultdict(Counter) for f in FIELDS} for s in ("dev", "val")}
    for tid in sorted(tasks):
        t = tasks[tid]
        c = clf.classify(EngTaskRequest(task_id=tid, query=t["query"], repository=t["repository"]))
        pred = {f: str(getattr(getattr(c, f), "value", getattr(c, f))) for f in FIELDS}
        per_task[tid] = {"split": split_of[tid], "label": {f: t[f] for f in FIELDS}, "predicted": pred}
        for f in FIELDS:
            conf[split_of[tid]][f][t[f]][pred[f]] += 1
    acc = {s: {f: sum(1 for r in per_task.values() if r["split"] == s and r["label"][f] == r["predicted"][f])
               for f in FIELDS} for s in ("dev", "val")}
    n = {s: sum(1 for r in per_task.values() if r["split"] == s) for s in ("dev", "val")}
    all_four = {s: sum(1 for r in per_task.values() if r["split"] == s and r["label"] == r["predicted"])
                for s in ("dev", "val")}
    return {"n": n, "correct": acc, "all_four_correct": all_four,
            "accuracy": {s: {f: acc[s][f] / n[s] for f in FIELDS} for s in acc},
            "confusion": {s: {f: {k: dict(v) for k, v in m.items()} for f, m in d.items()} for s, d in conf.items()},
            "per_task": per_task}


def markdown(res: Dict[str, Any], run_id: str) -> str:
    lines = [f"# Classifier vs benchmark labels ({run_id})", "",
             "Dev = where rules are improved; val = untouched check. Benchmark labels are pilot labels "
             "still under review.", "", "| Split | n | stage | task type | complexity | criticality | all four |",
             "|---|---|---|---|---|---|---|"]
    for s in ("dev", "val"):
        c, n = res["correct"][s], res["n"][s]
        lines.append(f"| {s} | {n} | " + " | ".join(f"{c[f]}/{n}" for f in FIELDS)
                     + f" | {res['all_four_correct'][s]}/{n} |")
    for s in ("dev", "val"):
        for f in FIELDS:
            m = res["confusion"][s][f]
            cols = sorted({p for row in m.values() for p in row})
            lines += ["", f"### {s} · {f} (rows: benchmark label, columns: classifier)", "",
                      "| label \\ predicted | " + " | ".join(cols) + " |", "|---|" + "---|" * len(cols)]
            for lab in sorted(m):
                lines.append(f"| {lab} | " + " | ".join(str(m[lab].get(p, 0)) for p in cols) + " |")
    return "\n".join(lines) + "\n"


def main(argv=None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--run-id", required=True)
    p.add_argument("--machine", default="machine_A")
    args = p.parse_args(argv)
    res = evaluate()
    res["created_utc"] = datetime.now(timezone.utc).isoformat()
    out = OUT_ROOT / args.machine / args.run_id
    out.mkdir(parents=True, exist_ok=True)
    (out / "result.json").write_text(json.dumps(res, indent=2) + "\n", encoding="utf-8")
    md = markdown(res, args.run_id)
    (out / "report.md").write_text(md, encoding="utf-8")
    print("\n".join(md.splitlines()[:8]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
