"""
Engineering Intelligence Hub — Statistical Analysis & Pareto Engine (Phase-2 M5)
================================================================================
Computes statistical comparisons, paired differences, ablation transition deltas,
multi-dimensional breakdowns, and 2D Pareto efficiency frontiers across systems.

Ablation Transitions:
  - Delta(A -> B) : Effect of adding retrieval
  - Delta(B -> C) : Effect of task-aware adaptive routing
  - Delta(C -> D) : Effect of knowledge graph context
  - Delta(D -> E) : Effect of quality verification + bounded escalation
"""

from __future__ import annotations

import math
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from pydantic import BaseModel, ConfigDict


class AblationDelta(BaseModel):
    """Transition delta between two experimental configurations."""
    transition: str  # e.g. "A -> B", "B -> C", "C -> D", "D -> E"
    source_system: str
    target_system: str
    delta_quality: Optional[float]
    delta_latency_ms: float
    delta_total_tokens: float
    delta_energy_joules: float
    delta_cost_usd: float
    delta_co2e_grams: float
    delta_quality_per_joule: Optional[float]

    model_config = ConfigDict(use_enum_values=True)


class ParetoPoint(BaseModel):
    """A point in the 2D efficiency trade-off space."""
    system_id: str
    system_name: str
    quality: float
    resource_cost: float
    is_non_dominated: bool = False

    model_config = ConfigDict(use_enum_values=True)


def compute_system_summary(task_aggregates: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    System-level mean and std dev across tasks. Quality figures use only tasks whose trials
    were scored (a task without any scored trial has None and is counted, never filled).
    """
    if not task_aggregates:
        return {}

    n = len(task_aggregates)

    def _vals(key: str) -> List[float]:
        return [t[key] for t in task_aggregates if t.get(key) is not None]

    def _mean(key: str) -> Optional[float]:
        v = _vals(key)
        return sum(v) / len(v) if v else None

    def _std(key: str, m: Optional[float]) -> Optional[float]:
        v = _vals(key)
        if m is None:
            return None
        if len(v) <= 1:
            return 0.0
        return math.sqrt(sum((x - m) ** 2 for x in v) / (len(v) - 1))

    def _r(x: Optional[float], nd: int) -> Optional[float]:
        return None if x is None else round(x, nd)

    q_m = _mean("composite_quality_mean")
    lat_m = _mean("latency_ms_mean")
    tok_m = _mean("total_tokens_mean")
    en_m = _mean("total_energy_joules_mean")
    cost_m = _mean("cost_usd_mean")
    co2_m = _mean("co2e_grams_mean")

    return {
        "tasks_count": n,
        "tasks_without_scored_trials": sum(1 for t in task_aggregates if t.get("composite_quality_mean") is None),
        "trials_missing_scores": sum(t.get("trials_missing_scores", 0) for t in task_aggregates),
        "composite_quality_mean": _r(q_m, 4),
        "composite_quality_std": _r(_std("composite_quality_mean", q_m), 4),
        "pass_rate_mean": _r(_mean("pass_rate"), 4),
        "quality_constrained_success_rate": _r(_mean("quality_constrained_success_rate"), 4),
        "latency_ms_mean": _r(lat_m, 2),
        "latency_ms_std": _r(_std("latency_ms_mean", lat_m), 2),
        "total_tokens_mean": _r(tok_m, 1),
        "total_tokens_std": _r(_std("total_tokens_mean", tok_m), 1),
        "total_energy_joules_mean": _r(en_m, 4),
        "total_energy_joules_std": _r(_std("total_energy_joules_mean", en_m), 4),
        "cost_usd_mean": _r(cost_m, 6),
        "cost_usd_std": _r(_std("cost_usd_mean", cost_m), 6),
        "co2e_grams_mean": _r(co2_m, 6),
        "co2e_grams_std": _r(_std("co2e_grams_mean", co2_m), 6),
        "quality_per_joule_mean": _r(_mean("quality_per_joule_mean"), 4),
    }


def co2e_per_successful_task(
    trials: Sequence[Any],
    carbon_intensity_gco2_per_kwh: float,
    success: Callable[[Any], Optional[bool]] = lambda t: t.grounded_success,
) -> Dict[str, Any]:
    """
    The plan's headline metric (§9.3, contribution C4), [DERIVED]. Success is the PRIMARY
    definition decided on 2026-10-06 (A2): correct AND cites labelled evidence
    (TrialResult.grounded_success). Pass `success=lambda t: t.quality_constrained_success` for the
    secondary, gate-based definition.


        CO2e per successful task = (CO2e of ALL trials + CO2e of every model load/reload)
                                   / number of successful trials

    Every trial's energy was spent, so every trial counts in the numerator, including failures,
    refusals and trials with missing scores. Only trials whose success is True count in the
    denominator. Trials whose success is None (missing scores) are counted and reported, not
    guessed. Model loads (cold starts, routing reloads) are excluded from per-query energy
    (plan §10.4) but are part of the system's real cost, so they are added here.
    No success at all -> None (undefined), never infinity or zero.
    """
    trials = list(trials)
    outcomes = [success(t) for t in trials]
    trial_co2e = sum(t.co2e_grams for t in trials)
    load_j = sum((t.model_load_energy_joules or 0.0) for t in trials)
    load_co2e = load_j / 3_600_000.0 * carbon_intensity_gco2_per_kwh
    n_success = sum(1 for o in outcomes if o is True)
    total = trial_co2e + load_co2e
    return {
        "metric_tier": "DERIVED",
        "trials": len(trials),
        "successful_trials": n_success,
        "trials_success_unknown": sum(1 for o in outcomes if o is None),
        "trial_co2e_grams": round(trial_co2e, 6),
        "model_load_energy_joules": round(load_j, 4),
        "model_loads": sum(getattr(t, "model_loads", 0) for t in trials),
        "model_load_co2e_grams": round(load_co2e, 6),
        "total_co2e_grams": round(total, 6),
        "co2e_grams_per_successful_task": round(total / n_success, 6) if n_success else None,
        "success_rate": round(n_success / (len(trials) - sum(1 for o in outcomes if o is None)), 4)
        if len(trials) > sum(1 for o in outcomes if o is None) else None,
    }


def co2e_per_successful_task_by_system(
    trials: Sequence[Any], carbon_intensity_gco2_per_kwh: float,
    success: Callable[[Any], Optional[bool]] = lambda t: t.grounded_success,
) -> Dict[str, Dict[str, Any]]:
    by: Dict[str, List[Any]] = {}
    for t in trials:
        by.setdefault(t.system_id, []).append(t)
    return {sid: co2e_per_successful_task(ts, carbon_intensity_gco2_per_kwh, success) for sid, ts in sorted(by.items())}


def compute_ablation_deltas(
    system_summaries: Dict[str, Dict[str, Any]]
) -> List[AblationDelta]:
    """
    Calculate the 4 sequential transition deltas: A -> B, B -> C, C -> D, D -> E.
    """
    transitions = [
        ("A -> B (Add Fixed RAG)", "baseline_a", "baseline_b"),
        ("B -> C (Add Task-Aware Adaptive)", "baseline_b", "system_c"),
        ("C -> D (Add Knowledge Graph)", "system_c", "system_d"),
        ("D -> E (Add Quality Gate & Escalation)", "system_d", "system_e"),
    ]

    deltas: List[AblationDelta] = []
    for label, src, tgt in transitions:
        if src in system_summaries and tgt in system_summaries:
            s_s = system_summaries[src]
            s_t = system_summaries[tgt]

            deltas.append(
                AblationDelta(
                    transition=label,
                    source_system=src,
                    target_system=tgt,
                    delta_quality=(round(s_t["composite_quality_mean"] - s_s["composite_quality_mean"], 4)
                                   if s_t["composite_quality_mean"] is not None and s_s["composite_quality_mean"] is not None
                                   else None),
                    delta_latency_ms=round(s_t["latency_ms_mean"] - s_s["latency_ms_mean"], 2),
                    delta_total_tokens=round(s_t["total_tokens_mean"] - s_s["total_tokens_mean"], 1),
                    delta_energy_joules=round(s_t["total_energy_joules_mean"] - s_s["total_energy_joules_mean"], 4),
                    delta_cost_usd=round(s_t["cost_usd_mean"] - s_s["cost_usd_mean"], 6),
                    delta_co2e_grams=round(s_t["co2e_grams_mean"] - s_s["co2e_grams_mean"], 6),
                    delta_quality_per_joule=(round(s_t["quality_per_joule_mean"] - s_s["quality_per_joule_mean"], 4)
                                             if s_t["quality_per_joule_mean"] is not None and s_s["quality_per_joule_mean"] is not None
                                             else None),
                )
            )

    return deltas


def compute_pareto_frontier(
    points: List[Tuple[str, str, float, float]]
) -> List[ParetoPoint]:
    """
    Compute 2D Pareto frontier where we aim to MAXIMIZE Quality (x)
    and MINIMIZE Resource Cost (y).

    Parameters
    ----------
    points : List of (system_id, system_name, quality, resource_cost)

    Returns
    -------
    List[ParetoPoint] with is_non_dominated flag set.
    """
    pareto_list: List[ParetoPoint] = []

    for sid, sname, q, c in points:
        dominated = False
        for other_sid, _, other_q, other_c in points:
            if other_sid == sid:
                continue
            # other dominates if other_q >= q and other_c <= c with at least one strict inequality
            if (other_q >= q and other_c <= c) and (other_q > q or other_c < c):
                dominated = True
                break

        pareto_list.append(
            ParetoPoint(
                system_id=sid,
                system_name=sname,
                quality=round(q, 4),
                resource_cost=round(c, 4),
                is_non_dominated=not dominated,
            )
        )

    return pareto_list
