"""
Score cut-off calibration on dev + val (Step 2b; WORK_PLAN D17).

For every dev/val task, the strategy System C resolves for it is run with all cut-offs off
(dense and BM25 at the strategy's top_k), and each candidate is marked relevant if it overlaps a
labelled evidence span (draft labels). This gives the real score distributions of relevant and
irrelevant candidates:
  * fused score (strategy weights x dense cosine + BM25-normalised), for hybrid strategies
  * dense cosine, for dense-only strategies

The calibrated cut-off is the largest value (rounded down to 0.05) that keeps, for EVERY task, its
best-ranked relevant candidate. In words: no dev/val task loses all of its labelled evidence to
the cut-off. The share of irrelevant candidates each value removes is reported next to it.

    python -m experiments.threshold_calibration --run-id thresholds-2026-10-06
"""

from __future__ import annotations

import argparse
import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

REPO_ROOT = Path(__file__).resolve().parents[1]
OUT_ROOT = REPO_ROOT / "experiments" / "results" / "thresholds"


def _floor05(x: float) -> float:
    return math.floor(x * 20 + 1e-9) / 20


def collect() -> Dict[str, Any]:
    from benchmark.retrieval_labels import LABELS_PATH, load_dev_val_tasks
    from evaluation.retrieval_metrics import Label, RetrievedItem, _overlaps
    from experiments.mode_r import ModeRRunner
    from retrieval.strategies import RetrievalMode

    tasks, split_of = load_dev_val_tasks()
    labels = {d["task_id"]: Label.from_json(d)
              for d in json.loads(LABELS_PATH.read_text(encoding="utf-8"))["labels"]}
    r = ModeRRunner()
    dense, sparse = r.adaptive._dense, r.adaptive._sparse
    rows = []
    for tid in sorted(tasks):
        t = tasks[tid]
        clf = r.classify(t)
        strat = r.adaptive.resolve_strategy(clf)
        open_ = strat.model_copy(update={"score_threshold": 0.0})
        d = {c.chunk_id: c for c in dense.retrieve(query=t["query"], strategy=open_, task_id=tid).chunks}
        s = {c.chunk_id: c for c in sparse.retrieve(query=t["query"], strategy=open_, task_id=tid).chunks}
        cands = []
        for cid in set(d) | set(s):
            c = d.get(cid) or s.get(cid)
            md = c.metadata or {}
            item = RetrievedItem(c.source_path, md.get("start_line"), md.get("end_line"))
            ds = d[cid].score if cid in d else 0.0
            ss = s[cid].score if cid in s else 0.0
            cands.append({"chunk_id": cid, "dense": ds, "sparse": ss,
                          "fused": strat.dense_weight * ds + strat.sparse_weight * ss,
                          "relevant": bool(_overlaps(item, labels[tid])), "in_dense": cid in d, "in_sparse": cid in s})
        mode = str(getattr(strat.mode, "value", strat.mode))
        rows.append({"task_id": tid, "split": split_of[tid], "strategy": strat.strategy_name, "mode": mode,
                     "configured_threshold": strat.score_threshold, "top_k": strat.top_k,
                     "max_context_chunks": strat.max_context_chunks, "candidates": cands})
    return {"rows": rows}


def analyse(data: Dict[str, Any]) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    for family, key, modes in (("hybrid", "fused", {"hybrid", "graph_augmented"}), ("dense", "dense", {"dense"})):
        rows = [r for r in data["rows"] if r["mode"] in modes]
        if not rows:
            continue
        best_rel = []          # per task: score of its best relevant candidate
        no_relevant = []
        for r in rows:
            rel = [c[key] for c in r["candidates"] if c["relevant"]]
            if rel:
                best_rel.append(max(rel))
            else:
                no_relevant.append(r["task_id"])
        irr = [c[key] for r in rows for c in r["candidates"] if not c["relevant"]]
        rel_all = [c[key] for r in rows for c in r["candidates"] if c["relevant"]]
        tau = _floor05(min(best_rel)) if best_rel else 0.0

        def kept(th: float, vals: List[float]) -> float:
            return sum(1 for v in vals if v >= th) / len(vals) if vals else 0.0

        # zero-evidence count under the CONFIGURED thresholds (as built)
        zero_configured = sorted(r["task_id"] for r in rows
                                 if not any(c[key] >= r["configured_threshold"] for c in r["candidates"]))
        out[family] = {
            "tasks": len(rows), "tasks_without_relevant_candidate": no_relevant,
            "best_relevant_score_min": min(best_rel) if best_rel else None,
            "best_relevant_score_median": sorted(best_rel)[len(best_rel) // 2] if best_rel else None,
            "calibrated_threshold": tau,
            "share_relevant_kept_at_calibrated": kept(tau, rel_all),
            "share_irrelevant_removed_at_calibrated": 1 - kept(tau, irr),
            "configured_thresholds": sorted({r["configured_threshold"] for r in rows}),
            "zero_evidence_tasks_at_configured": zero_configured,
            "by_threshold": {f"{th:.2f}": {"relevant_kept": kept(th, rel_all), "irrelevant_removed": 1 - kept(th, irr),
                                           "tasks_losing_all_relevant": sum(1 for b in best_rel if b < th)}
                             for th in [x / 20 for x in range(0, 17)]},
        }
    return out


def main(argv=None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--run-id", required=True)
    p.add_argument("--machine", default="machine_A")
    args = p.parse_args(argv)
    data = collect()
    res = analyse(data)
    out = OUT_ROOT / args.machine / args.run_id
    out.mkdir(parents=True, exist_ok=True)
    (out / "candidates.json").write_text(json.dumps(data, indent=1) + "\n", encoding="utf-8")
    (out / "calibration.json").write_text(json.dumps({"created_utc": datetime.now(timezone.utc).isoformat(),
                                                      **res}, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: {kk: vv for kk, vv in v.items() if kk != "by_threshold"} for k, v in res.items()}, indent=2))
    for k, v in res.items():
        print(k, {th: (round(x["relevant_kept"], 2), round(x["irrelevant_removed"], 2), x["tasks_losing_all_relevant"])
                  for th, x in v["by_threshold"].items()})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
