"""
Engineering Intelligence Hub — Research Report Generator (Phase-2 M5)
======================================================================
Generates structured Markdown and JSON reports for comparative evaluations,
SDLC breakdowns, Pareto curves, ablation deltas, and failure distributions.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from experiments.m5.analysis import (
    AblationDelta,
    ParetoPoint,
    compute_ablation_deltas,
    compute_pareto_frontier,
    compute_system_summary,
)


def generate_markdown_report(
    summary_data: Dict[str, Any],
    output_path: Optional[Path] = None,
) -> str:
    """
    Generate comprehensive research Markdown report from processed summary data.
    """
    split_name = summary_data.get("split_name", "unknown")
    benchmark_ver = summary_data.get("benchmark_version", "v1.0")
    tasks_count = summary_data.get("tasks_evaluated", 0)
    trials_count = summary_data.get("trials_per_task", 1)
    aggregations = summary_data.get("aggregations", {})

    system_summaries: Dict[str, Dict[str, Any]] = {
        sys_id: compute_system_summary(task_aggs)
        for sys_id, task_aggs in aggregations.items()
    }

    # 1. System Comparison Table
    lines: List[str] = [
        f"# Phase-2 M5 Controlled Evaluation Report ({split_name.upper()} Split)",
        "",
        f"**Benchmark Version**: `{benchmark_ver}` | **Tasks Evaluated**: `{tasks_count}` | **Trials per Task**: `{trials_count}`",
        "",
        "## 1. System Performance Comparison",
        "",
        "| System ID | Quality (0-1) | QC Success Rate | Latency (ms) | Energy (J) | Cost ($) | CO2e (g) | Quality / Joule |",
        "|---|---|---|---|---|---|---|---|",
    ]

    for sys_id, s in sorted(system_summaries.items()):
        lines.append(
            f"| `{sys_id}` | {s.get('composite_quality_mean', 0.0):.3f} ± {s.get('composite_quality_std', 0.0):.3f} "
            f"| {s.get('quality_constrained_success_rate', 0.0):.1%} "
            f"| {s.get('latency_ms_mean', 0.0):.1f} ± {s.get('latency_ms_std', 0.0):.1f} "
            f"| {s.get('total_energy_joules_mean', 0.0):.3f} ± {s.get('total_energy_joules_std', 0.0):.3f} "
            f"| ${s.get('cost_usd_mean', 0.0):.6f} "
            f"| {s.get('co2e_grams_mean', 0.0):.6f} "
            f"| {s.get('quality_per_joule_mean', 0.0):.3f} |"
        )

    # 2. Ablation Analysis Deltas
    deltas = compute_ablation_deltas(system_summaries)
    lines.extend([
        "",
        "## 2. Stepwise Ablation Deltas",
        "",
        "| Transition | Delta Quality | Delta Latency (ms) | Delta Energy (J) | Delta Cost ($) | Delta CO2e (g) |",
        "|---|---|---|---|---|---|",
    ])
    for d in deltas:
        q_sign = "+" if d.delta_quality >= 0 else ""
        lat_sign = "+" if d.delta_latency_ms >= 0 else ""
        en_sign = "+" if d.delta_energy_joules >= 0 else ""
        lines.append(
            f"| **{d.transition}** | {q_sign}{d.delta_quality:.4f} | {lat_sign}{d.delta_latency_ms:.1f} "
            f"| {en_sign}{d.delta_energy_joules:.4f} | {d.delta_cost_usd:+.6f} | {d.delta_co2e_grams:+.6f} |"
        )

    # 3. 2D Pareto Frontier Analysis
    points_energy = [
        (sid, sid, s.get("composite_quality_mean", 0.0), s.get("total_energy_joules_mean", 0.0))
        for sid, s in system_summaries.items()
    ]
    pareto_en = compute_pareto_frontier(points_energy)

    lines.extend([
        "",
        "## 3. Pareto Efficiency Analysis (Quality vs Energy)",
        "",
        "| System ID | Quality (Max) | Total Energy J (Min) | Non-Dominated (Pareto)? |",
        "|---|---|---|---|",
    ])
    for p in pareto_en:
        status_str = "⭐ **YES**" if p.is_non_dominated else "No (Dominated)"
        lines.append(f"| `{p.system_id}` | {p.quality:.4f} | {p.resource_cost:.4f} J | {status_str} |")

    report_text = "\n".join(lines)

    if output_path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(report_text)

    return report_text
