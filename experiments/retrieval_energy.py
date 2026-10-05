"""
Retrieval energy by component, measured in batches (master prompt Step 1h; plan §2.2, §9.1).

A single retrieval takes ~0.1-1 s. The NVML energy counter advances in ~100 ms steps and polling
the GPU adds power (nvml_meter.py, OBSERVER EFFECT). So each component is run over all 36 dev/val
queries, `--repeats` times, inside ONE counter-only window (two counter reads, no polling), and
divided by the number of queries.

Per component:
  GPU gross J   [MEASURED]   NVML counter delta over the window
  GPU net J     [DERIVED]    gross - idle power x duration (idle measured the same way, same session)
  CPU J         [ESTIMATED]  CPU TDP x system-wide CPU utilisation x duration (psutil.cpu_times),
                             the runner's method; covers Qdrant and Neo4j (Docker, same CPU)

Components:
  embed_query            BGE-small query embedding (GPU)
  dense_search           Qdrant top-10 search with precomputed vectors (CPU in Docker)
  bm25                   BM25Plus over 53,905 chunks (CPU)
  rerank_top30           cross-encoder over the hybrid top-30 candidates (GPU)
  graph_increment        System E rung 2 with graph minus the same rung without graph
  baseline_b, system_c, system_d, system_e_esc1/esc2/esc_max   full retrieval as in Mode R

Thermal rule: if the GPU is above 90 C before a window, wait until it is at or below 65 C.

    python -m experiments.retrieval_energy --run-id retrieval-energy-2026-10-05 --repeats 5
"""

from __future__ import annotations

import argparse
import json
import platform
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List

import psutil

REPO_ROOT = Path(__file__).resolve().parents[1]
OUT_ROOT = REPO_ROOT / "experiments" / "results" / "retrieval_energy"
HOT_C, COOL_C = 90, 65


def _gpu_temp() -> int:
    import pynvml

    h = pynvml.nvmlDeviceGetHandleByIndex(0)
    return pynvml.nvmlDeviceGetTemperature(h, pynvml.NVML_TEMPERATURE_GPU)


def _cool_if_hot(log: List[Dict[str, Any]]) -> None:
    t = _gpu_temp()
    if t > HOT_C:
        t0 = time.perf_counter()
        while _gpu_temp() > COOL_C:
            time.sleep(5)
        log.append({"cooled_from_c": t, "waited_s": round(time.perf_counter() - t0, 1)})


def _cpu_util(a, b) -> float:
    total = sum(b) - sum(a)
    idle = (b.idle - a.idle) + (getattr(b, "iowait", 0.0) - getattr(a, "iowait", 0.0))
    return max(0.0, min(1.0, 1.0 - idle / total)) if total > 0 else 0.0


def measure(fn: Callable[[], None], repeats: int) -> Dict[str, Any]:
    from sustainability.energy.nvml_meter import NvmlEnergyMeter

    meter = NvmlEnergyMeter(sample_interval_s=3600.0)  # counter-only: no polling inside the window
    c0 = psutil.cpu_times()
    with meter:
        for _ in range(repeats):
            fn()
    m = meter.result
    return {"duration_s": m.duration_s, "gpu_gross_j": m.energy_j, "method": m.method,
            "cpu_utilisation": _cpu_util(c0, psutil.cpu_times()), "max_temp_c": m.max_temp_c}


def main(argv=None) -> int:
    from benchmark.retrieval_labels import load_dev_val_tasks
    from core.config import settings
    from experiments.m5.runner import baseline_b_strategy
    from experiments.mode_r import ModeRRunner, _git_commit
    from retrieval.adaptive import ExperimentMode
    from retrieval.reranker import get_reranker
    from retrieval.strategies import RerankerType, RetrievalMode
    from sustainability.energy.nvml_meter import nvml_available, wait_for_gpu_idle

    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--run-id", required=True)
    p.add_argument("--machine", default="machine_A")
    p.add_argument("--repeats", type=int, default=5)
    p.add_argument("--idle-seconds", type=float, default=30.0)
    args = p.parse_args(argv)
    if not nvml_available():
        raise SystemExit("NVML unavailable: nothing can be measured (no estimate is substituted)")

    tasks, _ = load_dev_val_tasks()
    tasks = [tasks[k] for k in sorted(tasks)]
    queries = [t["query"] for t in tasks]
    r = ModeRRunner()
    dense, sparse = r.adaptive._dense, r.adaptive._sparse
    clfs = [r.classify(t) for t in tasks]
    rungs = [r.rungs(c) for c in clfs]
    esc2_no_graph = [g["system_e_esc2"].model_copy(update={"include_graph_context": False,
                                                           "mode": RetrievalMode.HYBRID}) for g in rungs]
    reranker = get_reranker(RerankerType.CROSS_ENCODER.value)
    pool_strategy = baseline_b_strategy().model_copy(update={"top_k": 30, "max_context_chunks": 30})

    # Untimed warm-up of every component, and the inputs that components reuse.
    vectors = [dense.embedding_model.embed_text(q) for q in queries]
    pools = [r.hybrid_b.retrieve(query=q, strategy=pool_strategy, task_id="energy").chunks for q in queries]
    reranker.rerank(queries[0], pools[0], top_n=10)
    for sys in ("baseline_b", "system_c", "system_d", "system_e_esc1", "system_e_esc2", "system_e_esc_max"):
        r.retrieve(sys, tasks[0], clfs[0], rungs[0])

    def per_system(sys: str) -> Callable[[], None]:
        return lambda: [r.retrieve(sys, t, c, g) for t, c, g in zip(tasks, clfs, rungs)]

    components: Dict[str, Callable[[], None]] = {
        "embed_query": lambda: [dense.embedding_model.embed_text(q) for q in queries],
        "dense_search": lambda: [dense.vector_store.search(collection_name=dense.collection_name, query_vector=v,
                                                           top_k=10) for v in vectors],
        "bm25": lambda: [sparse.retrieve(query=q, strategy=baseline_b_strategy(), task_id="energy") for q in queries],
        "rerank_top30": lambda: [reranker.rerank(q, pool, top_n=10) for q, pool in zip(queries, pools)],
        "esc2_without_graph": lambda: [r.adaptive.retrieve(query=t["query"], classification=c,
                                                           experiment_mode=ExperimentMode.SYSTEM_D,
                                                           override_strategy=s, task_id="energy")
                                       for t, c, s in zip(tasks, clfs, esc2_no_graph)],
        **{s: per_system(s) for s in ("baseline_b", "system_c", "system_d", "system_e_esc1", "system_e_esc2",
                                      "system_e_esc_max")},
    }

    cooling: List[Dict[str, Any]] = []
    idle_state = wait_for_gpu_idle()
    idle = measure(lambda: time.sleep(args.idle_seconds), 1)
    idle_w = idle["gpu_gross_j"] / idle["duration_s"]
    n = len(queries) * args.repeats
    tdp = settings.sustainability.cpu_tdp_watts
    rows: Dict[str, Dict[str, Any]] = {}
    for name, fn in components.items():
        _cool_if_hot(cooling)
        m = measure(fn, args.repeats)
        net = m["gpu_gross_j"] - idle_w * m["duration_s"]
        rows[name] = {**m, "queries": n,
                      "gpu_gross_j_per_query": m["gpu_gross_j"] / n,
                      "gpu_net_j_per_query": net / n,
                      "cpu_j_per_query": tdp * m["cpu_utilisation"] * m["duration_s"] / n,
                      "ms_per_query": 1000.0 * m["duration_s"] / n}
    rows["graph_increment"] = {k: rows["system_e_esc2"][k] - rows["esc2_without_graph"][k]
                               for k in ("gpu_gross_j_per_query", "gpu_net_j_per_query", "cpu_j_per_query",
                                         "ms_per_query")}

    meta = {"study": "retrieval_energy_components", "run_id": args.run_id,
            "created_utc": datetime.now(timezone.utc).isoformat(), "git_commit": _git_commit(),
            "host": platform.node(), "queries": len(queries), "repeats": args.repeats,
            "idle": {**idle, "idle_power_w": idle_w, "settle": idle_state}, "cpu_tdp_watts": tdp,
            "collection": dense.collection_name, "cooling_events": cooling,
            "tiers": {"gpu_gross": "MEASURED", "gpu_net": "DERIVED", "cpu": "ESTIMATED"}}
    out = OUT_ROOT / args.machine / args.run_id
    out.mkdir(parents=True, exist_ok=True)
    (out / "run.json").write_text(json.dumps({**meta, "components": rows}, indent=2) + "\n", encoding="utf-8")
    lines = [f"# Retrieval energy per query, by component ({args.run_id})", "",
             f"{len(queries)} dev/val queries x {args.repeats} repeats per window; idle {idle_w:.2f} W "
             f"(measured over {idle['duration_s']:.0f} s, same counter-only method). "
             "GPU gross MEASURED, GPU net DERIVED, CPU ESTIMATED (TDP x utilisation).", "",
             "| Component | ms/query | GPU gross J/query | GPU net J/query | CPU J/query (est.) |",
             "|---|---|---|---|---|"]
    for name, v in rows.items():
        lines.append(f"| {name} | {v['ms_per_query']:.1f} | {v['gpu_gross_j_per_query']:.3f} | "
                     f"{v['gpu_net_j_per_query']:.3f} | {v['cpu_j_per_query']:.3f} |")
    lines += ["", "`graph_increment` = system_e_esc2 minus the same rung with graph context switched off.",
              f"Cooling events: {cooling or 'none'}."]
    (out / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
