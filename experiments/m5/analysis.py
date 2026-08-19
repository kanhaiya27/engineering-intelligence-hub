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
from typing import Any, Dict, List, Optional, Tuple

from pydantic import BaseModel, ConfigDict, Field


class AblationDelta(BaseModel):
    """Transition delta between two experimental configurations."""
    transition: str  # e.g. "A -> B", "B -> C", "C -> D", "D -> E"
    source_system: str
    target_system: str
    delta_quality: float
    delta_latency_ms: float
    delta_total_tokens: float
    delta_energy_joules: float
    delta_cost_usd: float
    delta_co2e_grams: float
    delta_quality_per_joule: float

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
    Compute system-level mean and std dev across all evaluated tasks.
    """
    if not task_aggregates:
        return {}

    n = len(task_aggregates)

    def _mean(key: str) -> float:
        return sum(t[key] for t in task_aggregates) / n

    def _std(key: str, m: float) -> float:
        if n <= 1:
            return 0.0
        return math.sqrt(sum((t[key] - m) ** 2 for t in task_aggregates) / (n - 1))

    q_m = _mean("composite_quality_mean")
    lat_m = _mean("latency_ms_mean")
    tok_m = _mean("total_tokens_mean")
    en_m = _mean("total_energy_joules_mean")
    cost_m = _mean("cost_usd_mean")
    co2_m = _mean("co2e_grams_mean")
    qpj_m = _mean("quality_per_joule_mean")
    pass_m = _mean("pass_rate")
    qc_m = _mean("quality_constrained_success_rate")

    return {
        "tasks_count": n,
        "composite_quality_mean": round(q_m, 4),
        "composite_quality_std": round(_std("composite_quality_mean", q_m), 4),
        "pass_rate_mean": round(pass_m, 4),
        "quality_constrained_success_rate": round(qc_m, 4),
        "latency_ms_mean": round(lat_m, 2),
        "latency_ms_std": round(_std("latency_ms_mean", lat_m), 2),
        "total_tokens_mean": round(tok_m, 1),
        "total_tokens_std": round(_std("total_tokens_mean", tok_m), 1),
        "total_energy_joules_mean": round(en_m, 4),
        "total_energy_joules_std": round(_std("total_energy_joules_mean", en_m), 4),
        "cost_usd_mean": round(cost_m, 6),
        "cost_usd_std": round(_std("cost_usd_mean", cost_m), 6),
        "co2e_grams_mean": round(co2_m, 6),
        "co2e_grams_std": round(_std("co2e_grams_mean", co2_m), 6),
        "quality_per_joule_mean": round(qpj_m, 4),
    }


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
                    delta_quality=round(s_t["composite_quality_mean"] - s_s["composite_quality_mean"], 4),
                    delta_latency_ms=round(s_t["latency_ms_mean"] - s_s["latency_ms_mean"], 2),
                    delta_total_tokens=round(s_t["total_tokens_mean"] - s_s["total_tokens_mean"], 1),
                    delta_energy_joules=round(s_t["total_energy_joules_mean"] - s_s["total_energy_joules_mean"], 4),
                    delta_cost_usd=round(s_t["cost_usd_mean"] - s_s["cost_usd_mean"], 6),
                    delta_co2e_grams=round(s_t["co2e_grams_mean"] - s_s["co2e_grams_mean"], 6),
                    delta_quality_per_joule=round(s_t["quality_per_joule_mean"] - s_s["quality_per_joule_mean"], 4),
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
