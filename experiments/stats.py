"""
Statistical tests for the system comparisons (master prompt Step 1c; plan §7.1 ablation deltas).

Unit of analysis: the TASK. Trials of one task are repeated measurements, not independent
samples, so each task's trials are first averaged (`task_means`). Comparisons are paired: the same
tasks under two systems.

  paired_comparison   mean/median paired difference, bootstrap 95% CI of the mean difference,
                      Wilcoxon signed-rank test (two-sided), matched-pairs rank-biserial r
                      and Cohen's d_z as effect sizes
  mcnemar_exact       paired binary outcomes (e.g. success yes/no per task): exact binomial test
                      on the discordant pairs
  holm                Holm-Bonferroni adjustment over a family of p-values
  compare_ladder      the plan's ablation transitions A->B, B->C, C->D, D->E (+ E->E_routed for RQ4),
                      Holm-adjusted as one family
  stratified          the same comparison inside each stratum (SDLC stage, complexity, criticality;
                      RQ5), Holm-adjusted across strata
  mixed_effects       score ~ system * stratum with a random intercept per task (statsmodels MixedLM;
                      RQ5's interaction test)

Nothing here imputes: a task missing under either system is dropped from that pair, and the
number used is reported.
"""

from __future__ import annotations

import math
import random
from typing import Any, Callable, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

LADDER: Tuple[Tuple[str, str, str], ...] = (
    ("A->B", "baseline_a", "baseline_b"),
    ("B->C", "baseline_b", "system_c"),
    ("C->D", "system_c", "system_d"),
    ("D->E", "system_d", "system_e"),
    ("E->E_routed", "system_e", "system_e_routed"),
)


def task_means(trials: Iterable[Any], value: Callable[[Any], Optional[float]]) -> Dict[str, Dict[str, float]]:
    """{system: {task: mean over that task's trials}}; trials with value None are skipped."""
    acc: Dict[Tuple[str, str], List[float]] = {}
    for t in trials:
        v = value(t)
        if v is not None:
            acc.setdefault((t.system_id, t.task_id), []).append(float(v))
    out: Dict[str, Dict[str, float]] = {}
    for (sid, tid), vs in acc.items():
        out.setdefault(sid, {})[tid] = sum(vs) / len(vs)
    return out


def bootstrap_ci(values: Sequence[float], stat: Callable[[Sequence[float]], float] = None,
                 n_resamples: int = 10_000, level: float = 0.95, seed: int = 42) -> Tuple[float, float]:
    """Percentile bootstrap CI (resampling tasks with replacement)."""
    if not values:
        raise ValueError("no values")
    stat = stat or (lambda v: sum(v) / len(v))
    rng = random.Random(seed)
    n = len(values)
    boots = sorted(stat([values[rng.randrange(n)] for _ in range(n)]) for _ in range(n_resamples))
    lo = boots[int(math.floor((1 - level) / 2 * n_resamples))]
    hi = boots[min(n_resamples - 1, int(math.ceil((1 + level) / 2 * n_resamples)) - 1)]
    return lo, hi


def rank_biserial(diffs: Sequence[float]) -> Optional[float]:
    """Matched-pairs rank-biserial correlation: (W+ - W-) / (W+ + W-), zeros dropped."""
    from scipy.stats import rankdata

    nz = [d for d in diffs if d != 0]
    if not nz:
        return None
    ranks = rankdata([abs(d) for d in nz])
    w_pos = sum(r for r, d in zip(ranks, nz) if d > 0)
    w_neg = sum(r for r, d in zip(ranks, nz) if d < 0)
    return (w_pos - w_neg) / (w_pos + w_neg)


def paired_comparison(a: Mapping[str, float], b: Mapping[str, float], n_resamples: int = 10_000,
                      seed: int = 42) -> Dict[str, Any]:
    """Compare system b against system a over the tasks both have (difference = b - a)."""
    from scipy.stats import wilcoxon

    tasks = sorted(set(a) & set(b))
    diffs = [b[t] - a[t] for t in tasks]
    out: Dict[str, Any] = {"n_tasks": len(tasks), "dropped_tasks": len(set(a) ^ set(b))}
    if len(tasks) < 2:
        return {**out, "mean_diff": None, "ci95": None, "wilcoxon_p": None, "rank_biserial": None, "cohens_dz": None}
    mean = sum(diffs) / len(diffs)
    sd = math.sqrt(sum((d - mean) ** 2 for d in diffs) / (len(diffs) - 1))
    nonzero = [d for d in diffs if d != 0]
    if nonzero:
        res = wilcoxon(diffs, zero_method="wilcox", alternative="two-sided")
        w, p = float(res.statistic), float(res.pvalue)
    else:
        w, p = None, 1.0  # identical on every task: no evidence of a difference
    s = sorted(diffs)
    median = s[len(s) // 2] if len(s) % 2 else (s[len(s) // 2 - 1] + s[len(s) // 2]) / 2
    return {
        **out,
        "mean_a": sum(a[t] for t in tasks) / len(tasks), "mean_b": sum(b[t] for t in tasks) / len(tasks),
        "mean_diff": mean, "median_diff": median,
        "ci95": bootstrap_ci(diffs, n_resamples=n_resamples, seed=seed),
        "wilcoxon_W": w, "wilcoxon_p": p, "n_nonzero": len(nonzero),
        "rank_biserial": rank_biserial(diffs),
        "cohens_dz": (mean / sd) if sd > 0 else None,
    }


def mcnemar_exact(a: Mapping[str, bool], b: Mapping[str, bool]) -> Dict[str, Any]:
    """Exact McNemar test for paired binary outcomes over the tasks both have."""
    from scipy.stats import binomtest

    tasks = sorted(set(a) & set(b))
    only_b = sum(1 for t in tasks if b[t] and not a[t])
    only_a = sum(1 for t in tasks if a[t] and not b[t])
    n = only_a + only_b
    p = 1.0 if n == 0 else float(binomtest(only_b, n, 0.5, alternative="two-sided").pvalue)
    return {"n_tasks": len(tasks), "b_only_success": only_b, "a_only_success": only_a, "p": p,
            "rate_a": sum(a[t] for t in tasks) / len(tasks) if tasks else None,
            "rate_b": sum(b[t] for t in tasks) / len(tasks) if tasks else None}


def holm(pvalues: Mapping[str, Optional[float]]) -> Dict[str, Optional[float]]:
    """Holm-Bonferroni adjusted p-values (monotone, capped at 1). None entries stay None."""
    items = sorted(((k, p) for k, p in pvalues.items() if p is not None), key=lambda kv: kv[1])
    m = len(items)
    out: Dict[str, Optional[float]] = {k: None for k, p in pvalues.items() if p is None}
    running = 0.0
    for i, (k, p) in enumerate(items):
        running = max(running, min(1.0, (m - i) * p))
        out[k] = running
    return out


def compare_ladder(per_task: Mapping[str, Mapping[str, float]],
                   transitions: Sequence[Tuple[str, str, str]] = LADDER, **kw) -> Dict[str, Dict[str, Any]]:
    """Paired comparison for each available transition, Holm-adjusted as one family."""
    res = {name: {"from": a, "to": b, **paired_comparison(per_task[a], per_task[b], **kw)}
           for name, a, b in transitions if a in per_task and b in per_task}
    adj = holm({k: v["wilcoxon_p"] for k, v in res.items()})
    for k in res:
        res[k]["wilcoxon_p_holm"] = adj[k]
    return res


def stratified(per_task: Mapping[str, Mapping[str, float]], strata: Mapping[str, str], system_a: str,
               system_b: str, **kw) -> Dict[str, Dict[str, Any]]:
    """Paired comparison of b vs a inside each stratum (task -> stratum), Holm across strata."""
    groups: Dict[str, List[str]] = {}
    for tid, s in strata.items():
        groups.setdefault(s, []).append(tid)
    res = {}
    for s, tids in sorted(groups.items()):
        a = {t: per_task[system_a][t] for t in tids if t in per_task[system_a]}
        b = {t: per_task[system_b][t] for t in tids if t in per_task[system_b]}
        res[s] = paired_comparison(a, b, **kw)
    adj = holm({k: v["wilcoxon_p"] for k, v in res.items()})
    for k in res:
        res[k]["wilcoxon_p_holm"] = adj[k]
    return res


def mixed_effects(per_task: Mapping[str, Mapping[str, float]], strata: Mapping[str, str],
                  systems: Sequence[str]) -> Dict[str, Any]:
    """score ~ C(system) * C(stratum) + (1 | task) by REML. Returns coefficients, p-values and
    a Wald test that every system x stratum interaction is zero (does the benefit vary by stratum?)."""
    import numpy as np
    import pandas as pd
    import statsmodels.formula.api as smf

    rows = [{"task": t, "system": s, "stratum": strata[t], "score": v}
            for s in systems for t, v in per_task.get(s, {}).items() if t in strata]
    df = pd.DataFrame(rows)
    if df.empty or df["system"].nunique() < 2 or df["stratum"].nunique() < 2:
        raise ValueError("need at least two systems and two strata")
    model = smf.mixedlm("score ~ C(system) * C(stratum)", df, groups=df["task"])
    fit = model.fit(reml=True)
    names = list(fit.params.index)
    inter = [i for i, n in enumerate(names) if ":" in n]
    wald = None
    if inter:
        r = np.zeros((len(inter), len(names)))
        for row, i in enumerate(inter):
            r[row, i] = 1.0
        w = fit.wald_test(r, scalar=True)
        wald = {"statistic": float(w.statistic), "p": float(w.pvalue), "df": len(inter)}
    return {"n_obs": int(len(df)), "n_tasks": int(df["task"].nunique()), "converged": bool(fit.converged),
            "params": {k: float(v) for k, v in fit.params.items()},
            "pvalues": {k: float(v) for k, v in fit.pvalues.items()},
            "interaction_wald": wald}


def min_detectable_effect(n_tasks: int, sd_diff: float, alpha: float = 0.05, power: float = 0.80) -> Optional[float]:
    """Smallest mean paired difference detectable with a two-sided paired test (normal approx.;
    the Wilcoxon test's asymptotic efficiency is ~0.955 of the t-test, so n is scaled by it).
    Used by Step 3d's power check."""
    from scipy.stats import norm

    if n_tasks < 2 or sd_diff <= 0:
        return None
    n_eff = n_tasks * 0.955
    return (norm.ppf(1 - alpha / 2) + norm.ppf(power)) * sd_diff / math.sqrt(n_eff)
