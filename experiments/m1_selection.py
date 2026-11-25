"""
M1: choose the correctness measure by agreement with blind human ratings (docs/M1_PROTOCOL.md).

Computes every candidate measure for the rated answers, inter-rater agreement, Spearman rho of each
candidate with mean human correctness (bootstrap CI), and the kappa-maximising threshold against
"both raters accept". It never reads which system wrote an answer and computes no per-system
numbers: the selection is fixed before any system is rescored.

    python -m experiments.m1_selection --batch m1-rating-01 [--with-judge]
"""

from __future__ import annotations

import argparse
import json
import random
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Dict, List, Optional, Sequence, Tuple

REPO_ROOT = Path(__file__).resolve().parents[1]
OUT_ROOT = REPO_ROOT / "experiments" / "results" / "m1"
_STOP = {"the", "and", "for", "with", "that", "this", "are", "was", "were", "from", "into", "when", "then",
         "than", "which", "will", "can", "has", "have", "had", "not", "but", "also", "its", "it's", "you", "your",
         "use", "used", "using", "such", "each", "any", "all", "via", "per", "may", "should", "would", "could",
         "does", "did", "done", "how", "what", "why", "where", "who", "their", "there", "these", "those", "them"}


_EMBED = None


def _tokens(text: str) -> List[str]:
    return [w for w in re.findall(r"[a-z0-9_]+", (text or "").lower()) if len(w) >= 3 and w not in _STOP]


def token_f1(answer: str, refs: Sequence[str]) -> float:
    from evaluation.scorers.correctness import CorrectnessEvaluator

    ev = CorrectnessEvaluator()
    return max(ev.compute_f1_score(answer, r) for r in refs)


def ref_recall(answer: str, refs: Sequence[str]) -> float:
    a = set(_tokens(answer))
    best = 0.0
    for r in refs:
        rt = set(_tokens(r))
        if rt:
            best = max(best, len(rt & a) / len(rt))
    return best


def semantic(answer: str, refs: Sequence[str], embed: Optional[Callable[[str], List[float]]] = None) -> float:
    import math

    if embed is None:
        global _EMBED
        if _EMBED is None:
            from knowledge.vector.embeddings import BGEEmbeddingModel

            _EMBED = BGEEmbeddingModel().embed_text
        embed = _EMBED
    va = embed(answer)
    best = -1.0
    for r in refs:
        vr = embed(r)
        dot = sum(x * y for x, y in zip(va, vr))
        na, nr = math.sqrt(sum(x * x for x in va)), math.sqrt(sum(y * y for y in vr))
        best = max(best, dot / (na * nr) if na and nr else 0.0)
    return best


JUDGE_PROMPT = ("You are checking an answer against a reference answer.\n\nQUESTION:\n{q}\n\nREFERENCE ANSWER:\n{r}\n\n"
                "ANSWER TO CHECK:\n{a}\n\nDoes the answer state the reference's key facts without contradicting "
                "them? Extra correct detail is fine. Reply with exactly one word: YES or NO.")


def llm_judge(question: str, answer: str, refs: Sequence[str], provider=None) -> float:
    from core.inference import inference_config
    from generation.base import GenerationRequest

    if provider is None:
        from generation.providers.factory import build_provider
        provider = build_provider("ollama")
    out = provider.generate(GenerationRequest(prompt=JUDGE_PROMPT.format(q=question, r=refs[0], a=answer),
                                              model_id=inference_config().fixed_model, max_tokens=4,
                                              temperature=0.0))
    return 1.0 if out.text.strip().upper().startswith("YES") else 0.0


def bootstrap(stat: Callable[[List[int]], Optional[float]], n: int, reps: int = 10_000, seed: int = 42):
    rng = random.Random(seed)
    vals = []
    for _ in range(reps):
        idx = [rng.randrange(n) for _ in range(n)]
        v = stat(idx)
        if v is not None:
            vals.append(v)
    vals.sort()
    if not vals:
        return None
    return vals[int(0.025 * len(vals))], vals[min(len(vals) - 1, int(0.975 * len(vals)))]


def best_threshold(scores: Sequence[float], human: Sequence[bool]) -> Tuple[Optional[float], Optional[float]]:
    """Cut-off maximising Cohen's kappa of (score >= t) vs human; midpoint of the best tied range."""
    from benchmark.review import cohen_kappa

    cands = sorted(set(scores))
    results = []
    for t in cands:
        k = cohen_kappa(["y" if s >= t else "n" for s in scores], ["y" if h else "n" for h in human])
        results.append((t, k if k is not None else -1.0))
    best = max(k for _, k in results)
    if best <= -1.0:
        return None, None
    tied = [t for t, k in results if k == best]
    return (min(tied) + max(tied)) / 2 if len(tied) > 1 else tied[0], best


def select(units: List[dict], ratings: List[dict], measures: Dict[str, List[float]]) -> dict:
    """units[i] has blind_id; ratings have blind_id, rater, correctness, accept; measures[name][i]."""
    from scipy.stats import spearmanr
    from sklearn.metrics import cohen_kappa_score

    from benchmark.review import cohen_kappa

    by = {}
    for r in ratings:
        by.setdefault(r["blind_id"], []).append(r)
    keep = [i for i, u in enumerate(units) if len(by.get(u["blind_id"], [])) >= 2]
    mean_c = [sum(r["correctness"] for r in by[units[i]["blind_id"]][:2]) / 2 for i in keep]
    both = [all(r["accept"] for r in by[units[i]["blind_id"]][:2]) for i in keep]
    r1 = [by[units[i]["blind_id"]][0] for i in keep]
    r2 = [by[units[i]["blind_id"]][1] for i in keep]
    inter = {"units_with_two_ratings": len(keep),
             "weighted_kappa_correctness": float(cohen_kappa_score([a["correctness"] for a in r1],
                                                                   [b["correctness"] for b in r2],
                                                                   weights="quadratic", labels=[1, 2, 3, 4, 5]))
             if keep else None,
             "kappa_accept": cohen_kappa([str(a["accept"]) for a in r1], [str(b["accept"]) for b in r2]) if keep else None,
             "human_correct_share": sum(both) / len(both) if both else None}
    out = {}
    for name, vals in measures.items():
        v = [vals[i] for i in keep]
        rho = float(spearmanr(v, mean_c).correlation) if len(set(v)) > 1 else None

        def rho_at(idx, v=v):
            xs, ys = [v[j] for j in idx], [mean_c[j] for j in idx]
            if len(set(xs)) < 2 or len(set(ys)) < 2:
                return None
            return float(spearmanr(xs, ys).correlation)

        t, k = best_threshold(v, both)
        out[name] = {"spearman_rho": rho, "rho_ci95": bootstrap(rho_at, len(v)) if rho is not None else None,
                     "threshold": t, "kappa_at_threshold": k}
    ranked = sorted((m for m in out if out[m]["spearman_rho"] is not None),
                    key=lambda m: out[m]["spearman_rho"], reverse=True)
    return {"inter_rater": inter, "candidates": out, "chosen": ranked[0] if ranked else None,
            "chosen_threshold": out[ranked[0]]["threshold"] if ranked else None}


def main(argv=None) -> int:
    from benchmark.rating import KEY_DIR, RatingBatch, RatingStore
    from benchmark.retrieval_labels import load_dev_val_tasks

    p = argparse.ArgumentParser()
    p.add_argument("--batch", required=True)
    p.add_argument("--with-judge", action="store_true")
    args = p.parse_args(argv)
    store = RatingStore()
    batch = next(b for b in store.batches() if b.batch_id == args.batch)
    key = json.loads((KEY_DIR / f"{args.batch}_key.json").read_text(encoding="utf-8"))
    task_of = {b: v["task_id"] for b, v in key.items()}           # system ids are never read
    tasks, _ = load_dev_val_tasks()
    units = [u.model_dump() for u in batch.units]
    refs = [[tasks[task_of[u["blind_id"]]]["ground_truth"]] + tasks[task_of[u["blind_id"]]].get("acceptable_alternatives", [])
            for u in units]
    measures = {"token_f1": [token_f1(u["answer"], r) for u, r in zip(units, refs)],
                "ref_recall": [ref_recall(u["answer"], r) for u, r in zip(units, refs)],
                "semantic": [semantic(u["answer"], r) for u, r in zip(units, refs)]}
    if args.with_judge:
        measures["llm_judge"] = [llm_judge(u["query"], u["answer"], r) for u, r in zip(units, refs)]
    ratings = [r.model_dump() for r in store.ratings() if r.batch_id == args.batch]
    res = {"created_utc": datetime.now(timezone.utc).isoformat(), "batch": args.batch,
           "protocol": "docs/M1_PROTOCOL.md", **select(units, ratings, measures), "measures_per_unit": measures}
    OUT_ROOT.mkdir(parents=True, exist_ok=True)
    (OUT_ROOT / f"{args.batch}_selection.json").write_text(json.dumps(res, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in res.items() if k != "measures_per_unit"}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
