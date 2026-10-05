"""
Mode R: retrieval-only evaluation on the dev + val retrieval labels (plan §7.4, Phase 5).

No generation. For every labelled dev/val task, each system's retrieval is run exactly as the
Mode Q runner runs it, and scored with evaluation/retrieval_metrics.py:

  baseline_b        fixed hybrid, top_k 5 (experiments.m5.runner.baseline_b_strategy)
  system_c          real classifier -> adaptive strategy, no graph
  system_d          real classifier -> adaptive strategy + knowledge graph (= System E attempt 0)
  system_e_esc1     E's escalation rung 1 (wider retrieval)
  system_e_esc2     E's escalation rung 2 (graph, hop 2)
  system_e_esc_max  E's escalation rung 3 (graph + cross-encoder reranking)

System A retrieves nothing and is not scored. E's rungs are scored as configurations. Whether E
reaches a rung depends on its quality gate, which only Mode Q runs.

Held-out protection: only dev and val tasks are loaded (benchmark.retrieval_labels.load_dev_val_tasks).

    python -m experiments.mode_r --run-id mode-r-devval-2026-10-05
"""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from evaluation.retrieval_metrics import (
    DEFAULT_KS, Label, file_level, items_from_chunks, mean_metrics, span_level,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
OUT_ROOT = REPO_ROOT / "experiments" / "results" / "mode_r"
SYSTEMS = ("baseline_b", "system_c", "system_d", "system_e_esc1", "system_e_esc2", "system_e_esc_max")


def _sha256(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _git_commit() -> Optional[str]:
    try:
        return subprocess.run(["git", "-C", str(REPO_ROOT), "rev-parse", "HEAD"], capture_output=True,
                              text=True, timeout=10).stdout.strip() or None
    except (OSError, subprocess.SubprocessError):
        return None


class ModeRRunner:
    """Builds every system's retriever once and returns a ranked RetrievalResult per (system, task)."""

    def __init__(self) -> None:
        from intelligence.classifier import RuleBasedTaskClassifier
        from knowledge.graph.neo4j import Neo4jGraphStore
        from core.config import settings
        from retrieval.adaptive import AdaptiveRetrievalPipeline
        from retrieval.hybrid import HybridRetriever
        from verification.config import VerificationConfig
        from verification.escalation import EscalationPolicy
        from experiments.m5.manifest import ExperimentManifest, SystemID

        gs = settings.graph_store
        self.graph_store = Neo4jGraphStore(uri=gs.uri, username=gs.username, password=gs.password)
        self.classifier = RuleBasedTaskClassifier()
        self.hybrid_b = HybridRetriever()
        self.adaptive = AdaptiveRetrievalPipeline(graph_store=self.graph_store)
        self.manifest = ExperimentManifest.create_default()
        max_esc = self.manifest.systems[SystemID.SYSTEM_E.value].max_escalations
        self.escalation = EscalationPolicy(VerificationConfig(max_escalation_attempts=max_esc))

    def classify(self, task: dict):
        from knowledge.schemas.tasks import EngTaskRequest

        return self.classifier.classify(EngTaskRequest(task_id=task["task_id"], query=task["query"],
                                                       repository=task["repository"]))

    def rungs(self, clf) -> Dict[str, Any]:
        base = self.adaptive.resolve_strategy(clf)
        esc1 = self.escalation.escalate(base, 1)
        esc2 = self.escalation.escalate(esc1, 2)
        esc_max = self.escalation.escalate(esc2, 3)
        return {"system_e_esc1": esc1, "system_e_esc2": esc2, "system_e_esc_max": esc_max}

    def retrieve(self, system: str, task: dict, clf, rungs: Dict[str, Any]):
        from experiments.m5.runner import baseline_b_strategy
        from retrieval.adaptive import ExperimentMode

        q, tid = task["query"], task["task_id"]
        if system == "baseline_b":
            return self.hybrid_b.retrieve(query=q, strategy=baseline_b_strategy(), task_id=tid)
        if system == "system_c":
            return self.adaptive.retrieve(query=q, classification=clf, experiment_mode=ExperimentMode.SYSTEM_C,
                                          task_id=tid)
        if system == "system_d":
            return self.adaptive.retrieve(query=q, classification=clf, experiment_mode=ExperimentMode.SYSTEM_D,
                                          task_id=tid)
        return self.adaptive.retrieve(query=q, classification=clf, experiment_mode=ExperimentMode.SYSTEM_D,
                                      override_strategy=rungs[system], task_id=tid)


def evaluate(results: Dict[Tuple[str, str], Any], labels: Dict[str, Label], ks=DEFAULT_KS) -> Dict[str, Any]:
    """Per-task and mean metrics for every system. `results[(system, task_id)]` = RetrievalResult."""
    per_task: Dict[str, Dict[str, Dict[str, Any]]] = {}
    for (system, tid), res in sorted(results.items()):
        items = items_from_chunks(res.chunks)
        per_task.setdefault(system, {})[tid] = {
            "file": file_level(items, labels[tid], ks),
            "span": span_level(items, labels[tid], ks),
            "span_incl_graph": span_level(items, labels[tid], ks, include_graph=True),
            "n_chunks": len(items),
            "n_graph_chunks": sum(1 for i in items if i.is_graph),
            "zero_evidence": len(items) == 0,
        }
    summary = {}
    for system, rows in per_task.items():
        summary[system] = {
            "tasks": len(rows),
            "zero_evidence_tasks": sorted(t for t, r in rows.items() if r["zero_evidence"]),
            "file": mean_metrics(r["file"] for r in rows.values()),
            "span": mean_metrics(r["span"] for r in rows.values()),
            "span_incl_graph": mean_metrics(r["span_incl_graph"] for r in rows.values()),
        }
    return {"per_task": per_task, "summary": summary}


def _fmt(x: float) -> str:
    return f"{x:.3f}"


def report_markdown(meta: Dict[str, Any], ev: Dict[str, Any], ks=DEFAULT_KS) -> str:
    lines = [
        f"# Mode R: dev + val retrieval ({meta['run_id']})",
        "",
        f"**Labels: {meta['label_status']}.** "
        + ("These are PROVISIONAL until the labels are human-verified (ASK_ME L1). "
           if meta["labels_verified"] < meta["tasks"] else "")
        + "Dev/val only; no test task was loaded.",
        "",
        f"- Tasks: {meta['tasks']} ({meta['splits']}); commit {meta['git_commit']}; manifest {meta['manifest_hash']}",
        f"- Collection {meta['collection']} ({meta['collection_points']} points); graph "
        f"{meta['graph']['total_nodes']} nodes / {meta['graph']['total_edges']} edges",
        f"- Labels file {meta['labels_sha256'][:19]}…",
        "",
        "Definitions: `evaluation/retrieval_metrics.py`. File level counts graph-context chunks (they name a file);",
        "span level counts only chunks with source text; Precision@K divides by K.",
        "",
    ]
    for level, title in (("file", "File level"), ("span", "Span level (text chunks)"),
                         ("span_incl_graph", "Span level incl. graph chunks")):
        cols = ["mrr"] + [f"{m}@{k}" for m in ("recall", "precision", "ndcg") for k in ks]
        lines += [f"## {title}", "", "| System | " + " | ".join(cols) + " |",
                  "|---|" + "---|" * len(cols)]
        for system in SYSTEMS:
            if system in ev["summary"]:
                m = ev["summary"][system][level]
                lines.append(f"| {system} | " + " | ".join(_fmt(m[c]) for c in cols) + " |")
        lines.append("")
    lines += ["## Zero-evidence tasks (no chunk retrieved)", ""]
    for system in SYSTEMS:
        if system in ev["summary"]:
            z = ev["summary"][system]["zero_evidence_tasks"]
            lines.append(f"- {system}: {len(z)}" + (f" ({', '.join(z)})" if z else ""))
    lines += ["", "## Retrieval latency per query (ms, warm)", "", "| System | mean | max |", "|---|---|---|"]
    for system in SYSTEMS:
        lat = meta["latency_ms"].get(system)
        if lat:
            lines.append(f"| {system} | {sum(lat) / len(lat):.0f} | {max(lat):.0f} |")
    return "\n".join(lines) + "\n"


def main(argv=None) -> int:
    from benchmark.retrieval_labels import LABELS_PATH, load_dev_val_tasks
    from core.config import settings

    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--run-id", required=True)
    p.add_argument("--machine", default="machine_A")
    p.add_argument("--systems", default=",".join(SYSTEMS))
    args = p.parse_args(argv)
    systems = [s for s in args.systems.split(",") if s]

    tasks, split_of = load_dev_val_tasks()
    label_json = json.loads(LABELS_PATH.read_text(encoding="utf-8"))
    labels = {d["task_id"]: Label.from_json(d) for d in label_json["labels"]}
    assert set(labels) == set(tasks), "labels must cover exactly the dev/val tasks"

    runner = ModeRRunner()
    preflight_graph = runner.graph_store.count_nodes("Repository")
    if preflight_graph < 6:
        raise SystemExit(f"knowledge graph has {preflight_graph} Repository nodes; expected 6")

    # Untimed warm-up: load encoders, BM25 index and reranker before anything is measured.
    t0 = time.perf_counter()
    warm = next(iter(tasks.values()))
    wclf = runner.classify(warm)
    wr = runner.rungs(wclf)
    for system in systems:
        runner.retrieve(system, warm, wclf, wr)
    warm_s = time.perf_counter() - t0

    results, latency, strategies, classifications = {}, {s: [] for s in systems}, {}, {}
    for tid in sorted(tasks):
        task = tasks[tid]
        clf = runner.classify(task)
        rungs = runner.rungs(clf)
        classifications[tid] = {k: str(getattr(getattr(clf, k), "value", getattr(clf, k)))
                                for k in ("sdlc_stage", "task_type", "complexity", "criticality")}
        for system in systems:
            t = time.perf_counter()
            res = runner.retrieve(system, task, clf, rungs)
            latency[system].append((time.perf_counter() - t) * 1000.0)
            results[(system, tid)] = res
            strategies[f"{system}|{tid}"] = res.strategy_used

    ev = evaluate(results, labels)
    statuses = [d["label_status"] for d in label_json["labels"]]
    from experiments.m5.manifest import ExperimentManifest

    meta = {
        "study": "mode_r_dev_val", "run_id": args.run_id, "created_utc": datetime.now(timezone.utc).isoformat(),
        "git_commit": _git_commit(), "host": platform.node(),
        "manifest_hash": ExperimentManifest.create_default().compute_hash(),
        "tasks": len(tasks), "splits": dict(sorted({s: sum(1 for v in split_of.values() if v == s)
                                                    for s in set(split_of.values())}.items())),
        "labels_file": str(LABELS_PATH.relative_to(REPO_ROOT)), "labels_sha256": _sha256(LABELS_PATH),
        "label_status": ", ".join(f"{n} {s}" for s, n in sorted(
            {s: statuses.count(s) for s in set(statuses)}.items())),
        "labels_verified": statuses.count("verified"),
        "collection": runner.adaptive._dense.collection_name,
        "collection_points": runner.adaptive._dense.vector_store.count(runner.adaptive._dense.collection_name),
        "graph": {"repository_nodes": preflight_graph, "total_nodes": runner.graph_store.count_nodes(),
                  "total_edges": runner.graph_store.count_edges()},
        "embedding_model": settings.vector_store.embedding_model,
        "warm_up_seconds": round(warm_s, 2), "latency_ms": {k: [round(x, 2) for x in v] for k, v in latency.items()},
        "systems": systems, "ks": list(DEFAULT_KS),
        "strategy_used": strategies, "classification": classifications,
        "ranked": {f"{s}|{t}": [{"file": i.file, "start_line": i.start_line, "end_line": i.end_line,
                                  "graph": i.is_graph} for i in items_from_chunks(r.chunks)]
                   for (s, t), r in results.items()},
    }
    out = OUT_ROOT / args.machine / args.run_id
    out.mkdir(parents=True, exist_ok=True)
    (out / "run.json").write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")
    (out / "metrics.json").write_text(json.dumps(ev, indent=2) + "\n", encoding="utf-8")
    (out / "report.md").write_text(report_markdown(meta, ev), encoding="utf-8")
    print((out / "report.md").read_text(encoding="utf-8"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
