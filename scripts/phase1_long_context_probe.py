"""
Engineering Intelligence Hub — Phase-1b long-context probe
==========================================================
Answers two questions before any real run can be configured:

  1. How long do real pipeline prompts get?   (--part sizes, no GPU)
     Every chunk in the Qdrant collection is formatted exactly as the pipeline
     formats evidence (`QualityAwareRAGPipeline._build_context_prompt`) and
     counted with the Qwen2.5-Coder tokenizer. Prompt length for N chunks is then
     overhead (system prompt + chat template + question, counted exactly) + the
     sum of N sampled chunks (DERIVED: Monte Carlo over the real chunk lengths,
     seed 42) and the absolute worst case (the N longest chunks).

  2. What does a long context cost on this GPU?   (--part gpu)
     For each model / layer placement / num_ctx, a real-corpus prompt filled to
     num_ctx − num_predict − 32 tokens (counted exactly, chat template included)
     is sent to Ollama /api/chat. Recorded per call: whether the model + KV cache
     stayed on the GPU (Ollama /api/ps), device-wide peak VRAM, prefill and decode
     tokens/s, NVML energy (counter read at start and end only, MEASURED),
     temperature and throttle reasons. Errors (OOM, timeouts) are kept as data.
     Encoders (BGE-small + cross-encoder) are resident unless --alone, as in the
     pipeline.

Usage:
  python -m scripts.phase1_long_context_probe --part sizes
  python -m scripts.phase1_long_context_probe --part gpu [--ctx 4096,8192,...]
         [--models qwen2.5-coder:7b] [--placements forced,default] [--warm 2]

Output (default dir experiments/results/phase1/machine_A):
  long_context_sizes.json/.md, long_context_probe.json/.md
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import statistics
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from core.config import PROJECT_ROOT, settings
from experiments.provenance import collect_provenance, write_json
from generation.rag import SYSTEM_PROMPT
from generation.tokens import ChatTokenCounter
from scripts.phase1_vram_study import Encoders, _get, _post, _stats, loaded_models, unload_all
from sustainability.energy.nvml_meter import NvmlEnergyMeter, wait_for_gpu_idle

OUT_DIR = PROJECT_ROOT / "experiments" / "results" / "phase1" / "machine_A"
TOKENIZER_MODEL = "qwen2.5-coder:7b"
QUESTION = (
    "Using only the repository evidence above, explain what the code in the evidence does, "
    "which functions call which, and point out any error handling it performs."
)
N_CHUNKS = [3, 5, 8, 10, 14, 15, 18, 20, 24]
MC_SAMPLES = 20000
NUM_PREDICT = 256
PROMPT_MARGIN = 32
# Thermal rule (set by the owner, 2026-10-05): work up to MAX_TEMP_C; a condition in
# which any call exceeds it is discarded (kept in the file), the GPU cools to
# RESUME_TEMP_C and the condition is repeated.
MAX_TEMP_C = 90
RESUME_TEMP_C = 65
MAX_THERMAL_RETRIES = 2
DEFAULT_CTX = [4096, 8192, 12288, 16384, 20480, 24576]


# --------------------------------------------------------------------------- corpus
def load_chunks() -> List[Any]:
    """All chunks as RetrievedChunk, in a fixed order (repository, artifact, index)."""
    from knowledge.schemas.tasks import RetrievedChunk
    from knowledge.vector.qdrant import QdrantVectorStore

    raw = QdrantVectorStore().scroll_all(settings.vector_store.collection_name)
    if not raw:  # scroll_all returns [] when Qdrant is down: never probe with empty prompts
        raise RuntimeError(f"No chunks from Qdrant collection '{settings.vector_store.collection_name}'. "
                           "Is the eih-qdrant container running?")
    raw.sort(key=lambda c: (c.repository or "", c.artifact_id or "", c.chunk_index or 0))
    out = []
    for c in raw:
        md = dict(c.metadata or {})
        md.setdefault("start_line", c.start_line)
        md.setdefault("end_line", c.end_line)
        out.append(RetrievedChunk(
            chunk_id=c.chunk_id, content=c.content, score=0.0, repository=c.repository,
            source_path=md.get("file_path") or md.get("source_path"), metadata=md,
        ))
    return out


def format_chunks(chunks: List[Any]) -> str:
    from generation.quality_rag import QualityAwareRAGPipeline

    return QualityAwareRAGPipeline._build_context_prompt(None, chunks)  # type: ignore[arg-type]


def messages_for(context_str: str, request_id: Optional[str] = None) -> List[Dict[str, str]]:
    query = QUESTION if request_id is None else f"[request {request_id}] {QUESTION}"
    user = (
        f"ENGINEERING QUESTION / TASK:\n{query}\n\n"
        f"RETRIEVED REPOSITORY EVIDENCE:\n{context_str}\n\n"
        f"Please provide your grounded engineering answer following the rules."
    )
    return [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": user}]


def chunk_token_counts(chunks: List[Any], counter: ChatTokenCounter) -> List[int]:
    tok = counter._load(counter.tokenizer_id(TOKENIZER_MODEL))
    texts = [format_chunks([c]) + "\n" for c in chunks]
    counts: List[int] = []
    for i in range(0, len(texts), 1000):
        counts += [len(ids) for ids in tok(texts[i:i + 1000], add_special_tokens=False)["input_ids"]]
    return counts


def _pct(values: List[int], q: float) -> int:
    s = sorted(values)
    return s[min(len(s) - 1, int(round(q * (len(s) - 1))))]


# --------------------------------------------------------------------------- part 1
def part_sizes(out: Path) -> None:
    counter = ChatTokenCounter()
    chunks = load_chunks()
    print(f"{len(chunks)} chunks loaded; counting tokens ...")
    counts = chunk_token_counts(chunks, counter)
    overhead = counter.count(TOKENIZER_MODEL, messages_for(""))
    rng = random.Random(42)
    by_repo: Dict[str, List[int]] = {}
    for c, n in zip(chunks, counts):
        by_repo.setdefault(c.repository or "unknown", []).append(n)

    def dist(v: List[int]) -> Dict[str, Any]:
        return {"n": len(v), "mean": round(statistics.fmean(v), 1), "p50": _pct(v, .5), "p90": _pct(v, .9),
                "p95": _pct(v, .95), "p99": _pct(v, .99), "max": max(v)}

    top = sorted(counts, reverse=True)
    prompts = {}
    for n in N_CHUNKS:
        sums = [overhead + sum(rng.choices(counts, k=n)) for _ in range(MC_SAMPLES)]
        prompts[str(n)] = {**{k: v for k, v in dist(sums).items() if k != "n"},
                           "worst_case_longest_n": overhead + sum(top[:n])}
    data = {
        "study": "phase1_long_context_sizes",
        "provenance": collect_provenance(include_ollama=False),
        "config": {"collection": settings.vector_store.collection_name, "tokenizer_for": TOKENIZER_MODEL,
                   "tokenizer": counter.tokenizer_id(TOKENIZER_MODEL), "mc_samples": MC_SAMPLES, "seed": 42,
                   "question": QUESTION, "chunk_format": "QualityAwareRAGPipeline._build_context_prompt"},
        "results": {
            "prompt_overhead_tokens": overhead,
            "chunk_tokens": dist(counts),
            "chunk_tokens_by_repository": {r: dist(v) for r, v in sorted(by_repo.items())},
            "prompt_tokens_for_n_chunks": prompts,
            "tiers": {"chunk_tokens": "MEASURED", "prompt_overhead_tokens": "MEASURED",
                      "prompt_tokens_for_n_chunks": "DERIVED (Monte Carlo over measured chunk lengths)"},
        },
    }
    write_json(out / "long_context_sizes.json", data)
    r = data["results"]
    lines = [
        "# Long-context probe, part 1 — prompt sizes from the real corpus",
        "",
        f"{len(chunks)} chunks in `{data['config']['collection']}`, formatted as the pipeline formats evidence "
        f"and counted with `{data['config']['tokenizer']}`. Prompt overhead (system prompt + chat template + "
        f"question): **{overhead} tokens** (MEASURED). Recorded {data['provenance']['recorded_at_utc']}.",
        "",
        "Tokens per formatted chunk (MEASURED):",
        "",
        "| Scope | n | mean | p50 | p90 | p95 | p99 | max |", "|---|---|---|---|---|---|---|---|",
    ]
    for name, d in [("all", r["chunk_tokens"])] + list(r["chunk_tokens_by_repository"].items()):
        lines.append(f"| {name} | {d['n']} | {d['mean']} | {d['p50']} | {d['p90']} | {d['p95']} | {d['p99']} | {d['max']} |")
    lines += ["", f"Prompt tokens for N evidence chunks (DERIVED: {MC_SAMPLES} random draws, seed 42; "
                  "worst case = the N longest chunks in the corpus):", "",
              "| N chunks | p50 | p90 | p95 | p99 | max drawn | worst case |", "|---|---|---|---|---|---|---|"]
    for n, d in prompts.items():
        lines.append(f"| {n} | {d['p50']} | {d['p90']} | {d['p95']} | {d['p99']} | {d['max']} | {d['worst_case_longest_n']} |")
    (out / "long_context_sizes.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))


# --------------------------------------------------------------------------- part 2
def gpu_temp() -> int:
    import pynvml  # type: ignore[import]

    pynvml.nvmlInit()
    return pynvml.nvmlDeviceGetTemperature(pynvml.nvmlDeviceGetHandleByIndex(0), pynvml.NVML_TEMPERATURE_GPU)


def cool_down(target_c: int = RESUME_TEMP_C, max_wait_s: float = 900.0) -> Dict[str, Any]:
    """Wait (models unloaded) until the GPU is at or below target_c. Temperature only; power is never polled."""
    unload_all()
    t0, start = time.perf_counter(), gpu_temp()
    temp = start
    while temp > target_c and time.perf_counter() - t0 < max_wait_s:
        time.sleep(5)
        temp = gpu_temp()
    print(f"  cooled {start} -> {temp} °C in {time.perf_counter() - t0:.0f}s", flush=True)
    return {"from_c": start, "to_c": temp, "waited_s": round(time.perf_counter() - t0, 1)}


def call_too_hot(trial: Dict[str, Any]) -> bool:
    return bool(trial["energy"] and (trial["energy"].get("max_temp_c") or 0) > MAX_TEMP_C)


def device_total_mib() -> Optional[int]:
    try:
        import pynvml  # type: ignore[import]

        pynvml.nvmlInit()
        return pynvml.nvmlDeviceGetMemoryInfo(pynvml.nvmlDeviceGetHandleByIndex(0)).total >> 20
    except Exception:  # noqa: BLE001
        return None


class FillerPrompt:
    """Real-corpus evidence, cut to an exact token target (chat template included)."""

    def __init__(self, chunks: List[Any], counter: ChatTokenCounter) -> None:
        self.chunks, self.counter = chunks, counter
        self.counts = chunk_token_counts(chunks[:4000], counter)

    def build(self, target_tokens: int) -> Dict[str, Any]:
        rid = str(uuid.uuid4())  # first in the user turn: defeats Ollama's prompt-prefix KV reuse
        n, total = 0, self.counter.count(TOKENIZER_MODEL, messages_for("", rid))
        while n < len(self.counts) and total + self.counts[n] <= target_tokens:
            total += self.counts[n]
            n += 1
        msgs = messages_for(format_chunks(self.chunks[:n]), rid)
        while self.counter.count(TOKENIZER_MODEL, msgs) > target_tokens and n > 0:
            n -= 1
            msgs = messages_for(format_chunks(self.chunks[:n]), rid)
        return {"messages": msgs, "n_chunks": n, "prompt_tokens": self.counter.count(TOKENIZER_MODEL, msgs)}


def chat(model: str, prompt: Dict[str, Any], options: Dict[str, Any]) -> Dict[str, Any]:
    meter = NvmlEnergyMeter()
    error, resp = None, {}
    t0 = time.perf_counter()
    with meter:
        try:
            resp = _post("/api/chat", {"model": model, "messages": prompt["messages"], "stream": False,
                                       "options": options, "keep_alive": "30m"}, timeout=1200.0)
        except Exception as exc:  # noqa: BLE001 - OOM / server errors are results
            error = f"{type(exc).__name__}: {exc}"
    wall = time.perf_counter() - t0
    ps = next((m for m in loaded_models() if m["name"] == model), None)
    ns = 1e9
    pc, ps_s = resp.get("prompt_eval_count"), (resp.get("prompt_eval_duration") or 0) / ns
    ec, es = resp.get("eval_count"), (resp.get("eval_duration") or 0) / ns
    content = (resp.get("message") or {}).get("content") or ""
    return {
        "error": error,
        "wall_s": wall,
        "prompt_tokens_counted": prompt["prompt_tokens"],
        "n_evidence_chunks": prompt["n_chunks"],
        "ollama": {"load_s": (resp.get("load_duration") or 0) / ns, "total_s": (resp.get("total_duration") or 0) / ns,
                   "prompt_eval_count": pc, "prompt_eval_s": ps_s, "eval_count": ec, "eval_s": es,
                   "done_reason": resp.get("done_reason")},
        "prompt_count_matches": (pc == prompt["prompt_tokens"]) if pc is not None else None,
        "prefill_tokens_per_s": pc / ps_s if pc and ps_s else None,
        "decode_tokens_per_s": ec / es if ec and es else None,
        "output_sha256": hashlib.sha256(content.encode()).hexdigest()[:16],
        "ps": {"size_bytes": ps.get("size") if ps else None, "size_vram_bytes": ps.get("size_vram") if ps else None,
               "fraction_on_gpu": (ps["size_vram"] / ps["size"]) if ps and ps.get("size") else None,
               "context_length": ps.get("context_length") if ps else None},
        "energy": meter.result.to_dict() if meter.result else None,
    }


def summarise(trials: List[Dict[str, Any]], total_mib: Optional[int]) -> Dict[str, Any]:
    ok = [t for t in trials if not t["error"]]
    peaks = [t["energy"]["peak_mem_used_mib"] for t in ok if t["energy"] and t["energy"]["peak_mem_used_mib"]]
    return {
        "n_ok": len(ok), "n_error": len(trials) - len(ok),
        "errors": sorted({t["error"] for t in trials if t["error"]}),
        "wall_s": _stats([t["wall_s"] for t in ok]),
        "prefill_tokens_per_s": _stats([t["prefill_tokens_per_s"] for t in ok]),
        "decode_tokens_per_s": _stats([t["decode_tokens_per_s"] for t in ok]),
        "energy_j_gross": _stats([t["energy"]["energy_j"] for t in ok if t["energy"]]),
        "prompt_tokens": _stats([t["ollama"]["prompt_eval_count"] for t in ok]),
        "prompt_count_all_match": all(t["prompt_count_matches"] for t in ok) if ok else None,
        "fraction_on_gpu_min": min((t["ps"]["fraction_on_gpu"] or 0) for t in ok) if ok else None,
        "peak_device_vram_mib": max(peaks) if peaks else None,
        # On Windows (WDDM) the driver can page VRAM to system RAM instead of failing:
        # a peak at the card's limit means the speed numbers may include that spill.
        "device_mem_saturated": bool(peaks and total_mib and max(peaks) >= total_mib - 128),
        "max_temp_c": max((t["energy"]["max_temp_c"] or 0) for t in ok if t["energy"]) if ok else None,
        "throttle_reasons_seen": sorted({r for t in ok if t["energy"] for r in t["energy"]["throttle_reasons_seen"]}),
    }


def part_gpu(out: Path, models: List[str], placements: List[str], ctxs: List[int], warm: int, alone: bool) -> None:
    counter = ChatTokenCounter()
    chunks = load_chunks()
    filler = FillerPrompt(chunks, counter)
    total_mib = device_total_mib()
    unload_all()
    encoders = None
    if not alone:
        print("== loading encoders (BGE-small + cross-encoder)", flush=True)
        encoders = Encoders(format_chunks(chunks[:200]))
        print(f"  {encoders.info}", flush=True)
    results: Dict[str, Any] = {}
    for model in models:
        for placement in placements:
            for ctx in ctxs:
                options = {"temperature": 0, "seed": 42, "num_predict": NUM_PREDICT, "num_ctx": ctx}
                if placement == "forced":
                    options["num_gpu"] = 999
                key = f"{model}|{placement}|{ctx}"
                print(f"- {key}", flush=True)
                discarded: List[Dict[str, Any]] = []
                cooldowns: List[Dict[str, Any]] = []
                for attempt in range(1 + MAX_THERMAL_RETRIES):
                    unload_all()
                    if gpu_temp() > MAX_TEMP_C:
                        cooldowns.append(cool_down())
                    settle = wait_for_gpu_idle()
                    temp_start = gpu_temp()
                    trials, too_hot = [], False
                    for i in range(1 + warm):  # trial 0 is cold (model load + KV allocation)
                        if encoders:
                            encoders.workload()
                        t = chat(model, filler.build(ctx - NUM_PREDICT - PROMPT_MARGIN), options)
                        t["cold"] = i == 0
                        trials.append(t)
                        print(f"  {'cold' if i == 0 else 'warm'}: {t['wall_s']:.1f}s prompt={t['ollama']['prompt_eval_count']} "
                              f"prefill={t['prefill_tokens_per_s'] or 0:.0f} decode={t['decode_tokens_per_s'] or 0:.1f} tok/s "
                              f"gpu={(t['ps']['fraction_on_gpu'] or 0) * 100:.0f}% "
                              f"peak={(t['energy'] or {}).get('peak_mem_used_mib')} MiB "
                              f"max={(t['energy'] or {}).get('max_temp_c')}°C err={t['error']}", flush=True)
                        if call_too_hot(t):
                            too_hot = True
                            break
                        if t["error"]:
                            break
                    if not too_hot:
                        break
                    print(f"  > {MAX_TEMP_C} °C: discarding this condition, cooling down and repeating", flush=True)
                    discarded.append({"attempt": attempt, "temp_c_at_start": temp_start, "trials": trials})
                    cooldowns.append(cool_down())
                results[key] = {
                    "model": model, "placement": placement, "num_ctx": ctx, "options": options,
                    "temp_c_at_start": temp_start, "idle_settle": settle, "thermal_ok": not too_hot,
                    "discarded_over_temp": discarded, "cooldowns": cooldowns,
                    "cold": summarise([t for t in trials if t["cold"]], total_mib),
                    "warm": summarise([t for t in trials if not t["cold"]], total_mib),
                    "trials": trials,
                }
    unload_all()
    data = {
        "study": "phase1_long_context_probe",
        "provenance": collect_provenance(),
        "config": {"models": models, "placements": placements, "num_ctx": ctxs, "warm": warm,
                   "num_predict": NUM_PREDICT, "prompt_target": f"num_ctx - {NUM_PREDICT} - {PROMPT_MARGIN}",
                   "thermal_rule": {"max_temp_c": MAX_TEMP_C, "resume_temp_c": RESUME_TEMP_C, "max_retries": MAX_THERMAL_RETRIES}, "encoders_resident": not alone, "question": QUESTION,
                   "device_total_mib": total_mib},
        "encoders": encoders.info if encoders else None,
        "results": results,
    }
    write_json(out / "long_context_probe.json", data)
    write_probe_markdown(out / "long_context_probe.md", data)
    print((out / "long_context_probe.md").read_text(encoding="utf-8"))


def write_probe_markdown(path: Path, data: Dict[str, Any]) -> None:
    p = data["provenance"]

    def f(stat, nd=1):
        return "—" if not stat else f"{stat['mean']:.{nd}f}"

    lines = [
        "# Long-context probe, part 2 — " + p["machine_id"],
        "",
        f"GPU {p['gpu']['name']} ({p['gpu']['vram_total_mib']} MiB), driver {p['gpu']['driver']}, "
        f"Ollama {p['ollama']['version']}, git `{(p['git']['sha'] or '')[:10]}`{' (dirty)' if p['git']['dirty'] else ''}, "
        f"recorded {p['recorded_at_utc']}. Encoders resident: {data['config']['encoders_resident']}. "
        f"Prompt = real corpus evidence filled to {data['config']['prompt_target']} tokens; temperature 0, seed 42, "
        f"num_predict {NUM_PREDICT}. Each condition starts unloaded; a condition with any call above {MAX_TEMP_C} °C "
        f"is discarded and repeated after cooling to {RESUME_TEMP_C} °C (start temperature in the JSON); 1 cold + "
        f"{data['config']['warm']} warm calls. Energy = NVML counter at start/end (MEASURED, GPU board, gross).",
        "",
        "| Model | Layers | num_ctx | Start °C | Prompt tok | On GPU | Peak device MiB | Saturated | Cold s | Warm s "
        "| Prefill tok/s | Decode tok/s | Warm J | Max °C | Throttle | Errors |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for r in data["results"].values():
        c, w = r["cold"], r["warm"]
        s = w if w["n_ok"] else c
        pct = s["fraction_on_gpu_min"]
        lines.append(
            f"| {r['model']} | {r['placement']} | {r['num_ctx']} | {r['temp_c_at_start']} | {f(s['prompt_tokens'], 0)} "
            f"| {'—' if pct is None else f'{pct * 100:.0f}%'} | {s['peak_device_vram_mib'] or '—'} "
            f"| {'YES' if s['device_mem_saturated'] else 'no'} | {f(c['wall_s'])} | {f(w['wall_s'])} "
            f"| {f(s['prefill_tokens_per_s'], 0)} | {f(s['decode_tokens_per_s'])} | {f(w['energy_j_gross'])} "
            f"| {s['max_temp_c'] or '—'} | {', '.join(s['throttle_reasons_seen']) or 'none'} "
            f"| {'; '.join(c['errors'] + w['errors']) or 'none'} |"
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--part", choices=["sizes", "gpu"], required=True)
    ap.add_argument("--models", default="qwen2.5-coder:7b")
    ap.add_argument("--placements", default="forced,default", help="forced = num_gpu 999; default = Ollama decides")
    ap.add_argument("--ctx", default=",".join(map(str, DEFAULT_CTX)))
    ap.add_argument("--warm", type=int, default=2)
    ap.add_argument("--alone", action="store_true", help="Do not load the encoders")
    ap.add_argument("--out", default=str(OUT_DIR))
    args = ap.parse_args()
    out = Path(args.out)
    if args.part == "sizes":
        part_sizes(out)
    else:
        part_gpu(out, [m.strip() for m in args.models.split(",") if m.strip()],
                 [p.strip() for p in args.placements.split(",") if p.strip()],
                 [int(c) for c in args.ctx.split(",") if c.strip()], args.warm, args.alone)


if __name__ == "__main__":
    main()
