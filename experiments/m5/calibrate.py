"""
Engineering Intelligence Hub — Validation Calibration & Parameter Selection (Phase-2 M5)
========================================================================================
Calibrates and evaluates candidate configurations on the 12-task Validation split.

Allowed Tuning Dimensions:
  - top_k: [4, 5, 6]
  - dense / sparse fusion weights: [(0.75, 0.25), (0.70, 0.30), (0.65, 0.35)]
  - graph_hop_depth: [1, 2]
  - max_escalation_attempts: [2, 3]
  - escalation_top_k_delta: [2, 3, 4]

Selection Rule:
  1. PRIMARY OBJECTIVE: Maximize Quality-Constrained Success Rate (Quality >= Threshold).
  2. SECONDARY OBJECTIVE: Among configurations satisfying the quality constraint,
     minimize Latency, Energy, Cost, and CO2e.
"""

from __future__ import annotations

import datetime
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict

from core.logging import get_logger
from experiments.m5.analysis import compute_system_summary
from experiments.m5.manifest import ExperimentManifest, SystemID
from experiments.m5.runner import M5BenchmarkRunner
from generation.base import BaseLLMProvider
from generation.providers.factory import build_provider

logger = get_logger(__name__)

CALIBRATION_DIR = Path("experiments/results/m5/calibration")


class CalibrationCandidate(BaseModel):
    """Specification of one candidate parameter set for Validation calibration."""
    candidate_id: str
    candidate_name: str
    description: str
    top_k: int = 5
    dense_weight: float = 0.70
    sparse_weight: float = 0.30
    graph_hop_depth: int = 2
    max_escalations: int = 2
    escalation_top_k_delta: int = 3

    model_config = ConfigDict(use_enum_values=True)


def get_standard_candidates() -> List[CalibrationCandidate]:
    """Return the 4 standard validation candidates."""
    return [
        CalibrationCandidate(
            candidate_id="cand_1_baseline_heuristic",
            candidate_name="Candidate 1: Baseline Heuristics (Default)",
            description="Default initial heuristic parameters (top_k=5, hop_depth=2, max_esc=2).",
            top_k=5,
            dense_weight=0.70,
            sparse_weight=0.30,
            graph_hop_depth=2,
            max_escalations=2,
            escalation_top_k_delta=3,
        ),
        CalibrationCandidate(
            candidate_id="cand_2_focused_context",
            candidate_name="Candidate 2: Focused Context (Low Footprint)",
            description="Tighter context window (top_k=4, dense=0.75, sparse=0.25, hop_depth=1) for lower latency.",
            top_k=4,
            dense_weight=0.75,
            sparse_weight=0.25,
            graph_hop_depth=1,
            max_escalations=2,
            escalation_top_k_delta=2,
        ),
        CalibrationCandidate(
            candidate_id="cand_3_expanded_context",
            candidate_name="Candidate 3: Expanded Context (High Recall)",
            description="Broader initial retrieval (top_k=6, dense=0.65, sparse=0.35, hop_depth=2) for high recall.",
            top_k=6,
            dense_weight=0.65,
            sparse_weight=0.35,
            graph_hop_depth=2,
            max_escalations=2,
            escalation_top_k_delta=3,
        ),
        CalibrationCandidate(
            candidate_id="cand_4_conservative_escalation",
            candidate_name="Candidate 4: Conservative Escalation (High Quality)",
            description="Standard initial retrieval with 3 escalation attempts and delta=4 for maximum quality.",
            top_k=5,
            dense_weight=0.70,
            sparse_weight=0.30,
            graph_hop_depth=2,
            max_escalations=3,
            escalation_top_k_delta=4,
        ),
    ]


class CalibrationEvaluator:
    """
    Executes and scores all calibration candidates on the Validation split.
    """

    def __init__(
        self,
        llm_provider: Optional[BaseLLMProvider] = None,
        output_dir: Optional[Path] = None,
    ) -> None:
        self.llm_provider = llm_provider or build_provider()
        self.output_dir = output_dir or CALIBRATION_DIR
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def evaluate_candidate(
        self,
        candidate: CalibrationCandidate,
        trials_count: int = 3,
        max_tasks: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Run Validation split for one candidate and return aggregated performance.
        """
        # Create custom manifest for this candidate
        manifest = ExperimentManifest.create_default()
        manifest.systems[SystemID.BASELINE_B.value].default_top_k = candidate.top_k
        manifest.systems[SystemID.BASELINE_B.value].default_dense_weight = candidate.dense_weight
        manifest.systems[SystemID.BASELINE_B.value].default_sparse_weight = candidate.sparse_weight
        manifest.systems[SystemID.SYSTEM_E.value].max_escalations = candidate.max_escalations

        raw_cand_dir = self.output_dir / "raw" / candidate.candidate_id
        proc_cand_dir = self.output_dir / "processed" / candidate.candidate_id

        runner = M5BenchmarkRunner(
            manifest=manifest,
            llm_provider=self.llm_provider,
            raw_output_dir=raw_cand_dir,
            processed_output_dir=proc_cand_dir,
        )

        # Run Validation split
        summary = runner.run_split(
            split_name="val",
            trials_count=trials_count,
            max_tasks=max_tasks,
        )

        # System E performance summary is primary for calibration
        sys_e_aggs = summary["aggregations"].get(SystemID.SYSTEM_E.value, [])
        sys_e_summary = compute_system_summary(sys_e_aggs)

        return {
            "candidate": candidate.model_dump(),
            "manifest_hash": manifest.compute_hash(),
            "system_e_performance": sys_e_summary,
            "all_systems_summary": {
                sys_id: compute_system_summary(task_aggs)
                for sys_id, task_aggs in summary["aggregations"].items()
            },
        }

    def run_full_calibration(
        self,
        candidates: Optional[List[CalibrationCandidate]] = None,
        trials_count: int = 3,
    ) -> Dict[str, Any]:
        """
        Evaluate all candidates on the Validation split and select the optimal configuration.
        """
        cand_list = candidates or get_standard_candidates()
        results: List[Dict[str, Any]] = []

        logger.info(f"Starting Validation calibration over {len(cand_list)} candidates...")

        for cand in cand_list:
            logger.info(f"Evaluating {cand.candidate_name}...")
            res = self.evaluate_candidate(cand, trials_count=trials_count)
            results.append(res)

        # Selection Logic:
        # 1. Primary: Highest Quality-Constrained Success Rate on System E
        # 2. Secondary: Highest Composite Quality Mean
        # 3. Tertiary: Lowest Total Energy
        sorted_candidates = sorted(
            results,
            key=lambda r: (
                r["system_e_performance"].get("quality_constrained_success_rate", 0.0),
                r["system_e_performance"].get("composite_quality_mean", 0.0),
                -r["system_e_performance"].get("total_energy_joules_mean", float("inf")),
            ),
            reverse=True,
        )

        winning_result = sorted_candidates[0]

        calibration_report = {
            "timestamp": datetime.datetime.utcnow().isoformat(),
            "validation_tasks_evaluated": 12,
            "trials_per_task": trials_count,
            "candidates_evaluated": len(results),
            "winning_candidate": winning_result["candidate"],
            "winning_manifest_hash": winning_result["manifest_hash"],
            "winning_system_e_performance": winning_result["system_e_performance"],
            "selection_rationale": (
                f"Selected '{winning_result['candidate']['candidate_name']}' because it achieved "
                f"the highest Quality-Constrained Success Rate ({winning_result['system_e_performance'].get('quality_constrained_success_rate', 0.0):.1%}) "
                f"with Composite Quality = {winning_result['system_e_performance'].get('composite_quality_mean', 0.0):.4f} and "
                f"Energy = {winning_result['system_e_performance'].get('total_energy_joules_mean', 0.0):.4f} J."
            ),
            "all_candidate_results": results,
        }

        # Save calibration summary
        summary_path = self.output_dir / "calibration_summary.json"
        with open(summary_path, "w", encoding="utf-8") as f:
            json.dump(calibration_report, f, indent=2)

        logger.info(
            f"Calibration complete. Winning candidate: {winning_result['candidate']['candidate_id']} "
            f"(Hash: {winning_result['manifest_hash']})"
        )

        return calibration_report
