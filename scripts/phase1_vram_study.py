"""
Engineering Intelligence Hub — Phase-1 VRAM / throughput / energy study
=======================================================================
Measures, for each local Ollama model (qwen2.5-coder 1.5b / 3b / 7b, Q4_K_M):

  * VRAM: Ollama's own report of bytes resident on the GPU (`/api/ps size_vram`)
    and the device-wide peak from NVML during every call
  * cold (model load included) vs warm latency
  * decode and prefill tokens/sec (from Ollama's own timing fields)
  * GPU energy per generation from the NVML energy counter (MEASURED), gross and
    net of a separately measured idle baseline (DERIVED)
  * GPU temperature, SM clock range and throttle reasons per call

under two conditions:

  alone       — nothing else of ours on the GPU; runs FIRST, before torch has
                created a CUDA context in this process
  coresident  — BGE-small embeddings and the cross-encoder reranker are loaded
                first (pipeline order), then the LLM is loaded and called; each
                trial also runs one embed + rerank, as the pipeline would

Usage:  python -m scripts.phase1_vram_study [--cold 3] [--warm 5] [--out DIR]

Output: <out>/vram_study.json (all raw trials + summaries + provenance) and
        <out>/vram_study.md (summary tables). Default out:
        experiments/results/phase1/machine_A
"""

from __future__ import annotations

import argparse
import hashlib
import json
import statistics
import time
import urllib.request
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from core.config import PROJECT_ROOT, settings
from experiments.provenance import collect_provenance, write_json
from sustainability.energy.nvml_meter import NvmlEnergyMeter, measure_idle_power, wait_for_gpu_idle

MODELS = ["qwen2.5-coder:1.5b", "qwen2.5-coder:3b", "qwen2.5-coder:7b"]
OPTIONS = {"temperature": 0, "seed": 42, "num_predict": 128, "num_ctx": 4096}
CONTEXT_FILE = PROJECT_ROOT / "scripts" / "fixtures" / "phase1_prompt_context.txt"
QUESTION = (
    "Using only the documentation above, explain in detail how Flask's application "
    "context is pushed and popped during a request, what `current_app` and `g` are, "
    "and why accessing them outside a context raises an error."
)
RERANK_CANDIDATES = 20
IDLE_SECONDS = 8.0
BASE_URL = (settings.secrets.local_model_base_url or "http://localhost:11434").rstrip("/")


# --------------------------------------------------------------------------- ollama
def _post(path: str, body: Dict[str, Any], timeout: float = 600.0) -> Dict[str, Any]:
    req = urllib.request.Request(
        f"{BASE_URL}{path}", data=json.dumps(body).encode(), headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)


def _get(path: str) -> Dict[str, Any]:
    with urllib.request.urlopen(f"{BASE_URL}{path}", timeout=30) as r:
        return json.load(r)


def loaded_models() -> List[Dict[str, Any]]:
    return _get("/api/ps").get("models", [])


def unload_all() -> None:
    for m in loaded_models():
        _post("/api/generate", {"model": m["name"], "keep_alive": 0})
    for _ in range(100):
        if not loaded_models():
            return
        time.sleep(0.2)
    raise RuntimeError(f"Ollama models still loaded after unload: {loaded_models()}")


def build_prompt(context: str) -> str:
    # A unique id at the very START defeats Ollama's prompt-prefix KV reuse, so
    # every call pays a real prefill, as distinct pipeline queries would.
    return f"Request id: {uuid.uuid4()}\n\nDocumentation:\n{context}\n\nQuestion: {QUESTION}\n\nAnswer:"


def generate(model: str, prompt: str) -> Dict[str, Any]:
    vram_before = None
    try:
        import pynvml  # type: ignore[import]
        vram_before = pynvml.nvmlDeviceGetMemoryInfo(pynvml.nvmlDeviceGetHandleByIndex(0)).used >> 20
    except Exception:  # noqa: BLE001
        pass
    meter = NvmlEnergyMeter()
    error = None
    resp: Dict[str, Any] = {}
    t0 = time.perf_counter()
    with meter:
        try:
            resp = _post("/api/generate", {"model": model, "prompt": prompt, "stream": False,
                                           "options": OPTIONS, "keep_alive": "30m"})
        except Exception as exc:  # noqa: BLE001 - record OOM / server errors as data
            error = f"{type(exc).__name__}: {exc}"
    wall = time.perf_counter() - t0
    ps = next((m for m in loaded_models() if m["name"] == model), None)
    ns = 1e9
    eval_count = resp.get("eval_count")
    eval_s = (resp.get("eval_duration") or 0) / ns
    prompt_count = resp.get("prompt_eval_count")
    prompt_s = (resp.get("prompt_eval_duration") or 0) / ns
    energy = meter.result.to_dict() if meter.result else None
    return {
        "error": error,
        "wall_s": wall,
        "vram_used_before_mib": vram_before,
        "ollama": {
            "load_s": (resp.get("load_duration") or 0) / ns,
            "total_s": (resp.get("total_duration") or 0) / ns,
            "prompt_eval_count": prompt_count,
            "prompt_eval_s": prompt_s,
            "eval_count": eval_count,
            "eval_s": eval_s,
            "done_reason": resp.get("done_reason"),
        },
        "decode_tokens_per_s": (eval_count / eval_s) if eval_count and eval_s else None,
        "prefill_tokens_per_s": (prompt_count / prompt_s) if prompt_count and prompt_s else None,
        "output_sha256": hashlib.sha256((resp.get("response") or "").encode()).hexdigest()[:16],
        "ps": {
            "size_bytes": ps.get("size") if ps else None,
            "size_vram_bytes": ps.get("size_vram") if ps else None,
            "fraction_on_gpu": (ps["size_vram"] / ps["size"]) if ps and ps.get("size") else None,
            "context_length": ps.get("context_length") if ps else None,
        },
        "energy": energy,
    }


# --------------------------------------------------------------------------- encoders
class Encoders:
    """BGE-small + cross-encoder, loaded and exercised exactly as the pipeline does."""

    def __init__(self, context: str) -> None:
        import pynvml  # type: ignore[import]
        import torch

        from knowledge.schemas.tasks import RetrievedChunk
        from knowledge.vector.embeddings import BGEEmbeddingModel
        from retrieval.reranker import CrossEncoderReranker

        h = pynvml.nvmlDeviceGetHandleByIndex(0)
        before = pynvml.nvmlDeviceGetMemoryInfo(h).used >> 20
        self.embedder = BGEEmbeddingModel()
        self.reranker = CrossEncoderReranker()
        words = context.split()
        step = max(1, len(words) // RERANK_CANDIDATES)
        self.chunks = [
            RetrievedChunk(chunk_id=f"c{i}", content=" ".join(words[i * step:(i + 1) * step + 60]), score=0.0)
            for i in range(RERANK_CANDIDATES)
        ]
        self.workload()  # loads both models onto the GPU
        torch.cuda.synchronize()
        after = pynvml.nvmlDeviceGetMemoryInfo(h).used >> 20
        self.info = {
            "embedding_model": self.embedder.model_name,
            "reranker_model": self.reranker.model_id,
            "device_vram_before_mib": before,
            "device_vram_after_load_mib": after,
            "device_vram_delta_mib": after - before,
            "torch_allocated_mib": torch.cuda.memory_allocated() >> 20,
            "torch_reserved_mib": torch.cuda.memory_reserved() >> 20,
        }

    def workload(self) -> None:
        self.embedder.embed_text(QUESTION)
        self.reranker.rerank(QUESTION, [c.model_copy() for c in self.chunks], top_n=5)


# --------------------------------------------------------------------------- study
def _stats(values: List[Optional[float]]) -> Optional[Dict[str, float]]:
    vals = [v for v in values if v is not None]
    if not vals:
        return None
    return {
        "n": len(vals),
        "mean": statistics.fmean(vals),
        "stdev": statistics.stdev(vals) if len(vals) > 1 else 0.0,
        "min": min(vals),
        "max": max(vals),
    }


def summarise(trials: List[Dict[str, Any]], idle_w: Optional[float]) -> Dict[str, Any]:
    ok = [t for t in trials if not t["error"]]

    def energy(t):
        return t["energy"]["energy_j"] if t["energy"] else None

    def net(t):
        e = energy(t)
        return e - idle_w * t["energy"]["duration_s"] if e is not None and idle_w is not None else None

    def per_tok(t):
        e, n = energy(t), t["ollama"]["eval_count"]
        return e / n if e is not None and n else None

    return {
        "n_ok": len(ok),
        "n_error": len(trials) - len(ok),
        "errors": sorted({t["error"] for t in trials if t["error"]}),
        "wall_s": _stats([t["wall_s"] for t in ok]),
        "load_s": _stats([t["ollama"]["load_s"] for t in ok]),
        "decode_tokens_per_s": _stats([t["decode_tokens_per_s"] for t in ok]),
        "prefill_tokens_per_s": _stats([t["prefill_tokens_per_s"] for t in ok]),
        "eval_count": _stats([t["ollama"]["eval_count"] for t in ok]),
        "energy_j_gross": _stats([energy(t) for t in ok]),
        "energy_j_net_of_idle": _stats([net(t) for t in ok]),
        "energy_j_per_output_token": _stats([per_tok(t) for t in ok]),
        "peak_device_vram_mib": _stats([t["energy"]["peak_mem_used_mib"] for t in ok if t["energy"]]),
        "ollama_size_vram_mib": _stats([(t["ps"]["size_vram_bytes"] or 0) / 2**20 for t in ok]),
        "ollama_size_total_mib": _stats([(t["ps"]["size_bytes"] or 0) / 2**20 for t in ok]),
        "fraction_on_gpu_min": min((t["ps"]["fraction_on_gpu"] or 0) for t in ok) if ok else None,
        "max_temp_c": max((t["energy"]["max_temp_c"] or 0) for t in ok if t["energy"]) if ok else None,
        "min_sm_clock_mhz": min((t["energy"]["min_sm_clock_mhz"] or 0) for t in ok if t["energy"]) if ok else None,
        "throttle_reasons_seen": sorted({r for t in ok if t["energy"] for r in t["energy"]["throttle_reasons_seen"]}),
    }


def run_condition(model: str, context: str, cold: int, warm: int,
                  encoders: Optional[Encoders]) -> Dict[str, Any]:
    unload_all()
    settle_before = wait_for_gpu_idle()
    idle_before = measure_idle_power(IDLE_SECONDS)
    cold_trials, warm_trials, encoder_trials = [], [], []
    for i in range(cold):
        unload_all()
        time.sleep(1.0)
        if encoders:
            encoders.workload()
        cold_trials.append(generate(model, build_prompt(context)))
        print(f"  cold {i + 1}/{cold}: {cold_trials[-1]['wall_s']:.2f}s err={cold_trials[-1]['error']}")
    for i in range(warm):
        if encoders:
            m = NvmlEnergyMeter()
            with m:
                encoders.workload()
            encoder_trials.append(m.result.to_dict())
        warm_trials.append(generate(model, build_prompt(context)))
        print(f"  warm {i + 1}/{warm}: {warm_trials[-1]['wall_s']:.2f}s "
              f"{warm_trials[-1]['decode_tokens_per_s'] or 0:.1f} tok/s")
    total = cold_trials[-1]["ps"]["size_bytes"] if cold_trials else None
    vram = cold_trials[-1]["ps"]["size_vram_bytes"] if cold_trials else None
    # Idle is measured before AND after the condition, each time only once power
    # has settled; net energy uses their mean and the spread is reported.
    unload_all()
    settle_after = wait_for_gpu_idle()
    idle_after = measure_idle_power(IDLE_SECONDS)
    idles = [v for v in (idle_before, idle_after) if v is not None]
    idle_w = sum(idles) / len(idles) if idles else None
    print(f"  idle W before={idle_before} after={idle_after} (settled {settle_before['settled']}/{settle_after['settled']})")
    return {
        "idle_power_w": idle_w,
        "idle_power_before_w": idle_before,
        "idle_power_after_w": idle_after,
        "idle_settle_before": settle_before,
        "idle_settle_after": settle_after,
        "cold": {"trials": cold_trials, "summary": summarise(cold_trials, idle_w)},  # idle_w = mean(before, after)
        "warm": {"trials": warm_trials, "summary": summarise(warm_trials, idle_w)},
        "encoder_workload_energy": encoder_trials,
        "fully_on_gpu": bool(total and vram and vram >= total),
    }


def write_markdown(path: Path, data: Dict[str, Any]) -> None:
    p = data["provenance"]
    lines = [
        "# Phase-1 VRAM study — " + p["machine_id"],
        "",
        f"GPU {p['gpu']['name']} ({p['gpu']['vram_total_mib']} MiB), driver {p['gpu']['driver']}, "
        f"torch {p['torch']['torch']}, Ollama {p['ollama']['version']}, git `{(p['git']['sha'] or '')[:10]}`"
        f"{' (dirty)' if p['git']['dirty'] else ''}, recorded {p['recorded_at_utc']}.",
        "",
        f"Options: `{json.dumps(data['config']['options'])}`. Cold n={data['config']['cold']}, "
        f"warm n={data['config']['warm']}. Energy = NVML energy counter read only at call start and end "
        "(MEASURED, GPU board only; power is never polled during a measurement because it perturbs the "
        "counter on this driver, see nvml_observer_probe.json). Net = gross − idle power × duration "
        "(DERIVED; idle taken at P8 after settling). VRAM = device-wide (WDDM).",
        "",
        "| Model | Condition | On GPU | Ollama VRAM MiB | Peak device MiB | Cold s | Warm s | Decode tok/s | Prefill tok/s | Warm J gross | Warm J net | J/out-token | Max °C | Throttle |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|",
    ]

    def f(stat, key="mean", nd=1):
        return "—" if not stat else f"{stat[key]:.{nd}f}"

    for model, conds in data["results"].items():
        for cond, r in conds.items():
            c, w = r["cold"]["summary"], r["warm"]["summary"]
            pct = w["fraction_on_gpu_min"]
            lines.append(
                f"| {model} | {cond} | {'yes' if r['fully_on_gpu'] else 'NO'} ({(pct or 0) * 100:.0f}%) "
                f"| {f(w['ollama_size_vram_mib'], nd=0)} | {f(w['peak_device_vram_mib'], 'max', 0)} "
                f"| {f(c['wall_s'], nd=2)} | {f(w['wall_s'], nd=2)} | {f(w['decode_tokens_per_s'])} "
                f"| {f(w['prefill_tokens_per_s'], nd=0)} | {f(w['energy_j_gross'])} | {f(w['energy_j_net_of_idle'])} "
                f"| {f(w['energy_j_per_output_token'], nd=3)} | {w['max_temp_c']} | {', '.join(w['throttle_reasons_seen']) or 'none'} |"
            )
    lines += ["", "Idle baselines (W, measured after power settled; net energy uses their mean):", ""]
    for model, conds in data["results"].items():
        for cond, r in conds.items():
            sb, sa = r["idle_settle_before"], r["idle_settle_after"]
            lines.append(
                f"- {model} / {cond}: before {r['idle_power_before_w'] or float('nan'):.1f} "
                f"(P{sb.get('pstate')}, settled={sb.get('settled')}), after {r['idle_power_after_w'] or float('nan'):.1f} "
                f"(P{sa.get('pstate')}, settled={sa.get('settled')})"
            )
    enc = data.get("encoders")
    if enc:
        lines += ["", f"Encoders (BGE-small + cross-encoder) added {enc['device_vram_delta_mib']} MiB device VRAM "
                      f"(torch allocated {enc['torch_allocated_mib']} MiB, reserved {enc['torch_reserved_mib']} MiB)."]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cold", type=int, default=3)
    ap.add_argument("--warm", type=int, default=5)
    ap.add_argument("--models", default=",".join(MODELS))
    ap.add_argument("--out", default=str(PROJECT_ROOT / "experiments" / "results" / "phase1" / "machine_A"))
    ap.add_argument("--num-gpu", type=int, default=None,
                    help="Force Ollama to offload this many layers to the GPU (default: Ollama decides)")
    ap.add_argument("--conditions", default="alone,coresident")
    ap.add_argument("--out-name", default="vram_study", help="Output file stem")
    args = ap.parse_args()

    if args.num_gpu is not None:
        OPTIONS["num_gpu"] = args.num_gpu
    conditions = [c.strip() for c in args.conditions.split(",") if c.strip()]
    context = CONTEXT_FILE.read_text(encoding="utf-8")
    models = [m.strip() for m in args.models.split(",") if m.strip()]
    results: Dict[str, Dict[str, Any]] = {m: {} for m in models}

    if "alone" in conditions:
        print("== condition: alone (no torch CUDA context yet)")
        for m in models:
            print(f"- {m}")
            results[m]["alone"] = run_condition(m, context, args.cold, args.warm, None)

    encoders = None
    if "coresident" in conditions:
        print("== loading encoders (BGE-small + cross-encoder)")
        unload_all()
        encoders = Encoders(context)
        print(f"  encoders: {encoders.info}")
        print("== condition: coresident")
        for m in models:
            print(f"- {m}")
            results[m]["coresident"] = run_condition(m, context, args.cold, args.warm, encoders)

    unload_all()
    out = Path(args.out)
    data = {
        "study": "phase1_vram_study" if args.num_gpu is None else "phase1_vram_study_forced_gpu",
        "provenance": collect_provenance(),
        "config": {"options": OPTIONS, "cold": args.cold, "warm": args.warm, "models": models,
                   "context_file": str(CONTEXT_FILE.relative_to(PROJECT_ROOT)),
                   "context_sha256": hashlib.sha256(CONTEXT_FILE.read_bytes()).hexdigest(),
                   "question": QUESTION, "rerank_candidates": RERANK_CANDIDATES,
                   "idle_baseline_s": IDLE_SECONDS},
        "encoders": encoders.info if encoders else None,
        "results": results,
    }
    write_json(out / f"{args.out_name}.json", data)
    write_markdown(out / f"{args.out_name}.md", data)
    print(f"wrote {out / (args.out_name + '.json')} and {args.out_name}.md")


if __name__ == "__main__":
    main()
