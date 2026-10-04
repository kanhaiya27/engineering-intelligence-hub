"""
Engineering Intelligence Hub — Master Calibration Orchestrator (Phase-2 M5)
===========================================================================
Orchestrates the complete Phase-2 M5 calibration and evaluation pipeline:
  - Phase A: Development Experiment (24 tasks x 5 systems x 3 trials = 360 runs)
  - Phase B: Validation Calibration (12 tasks x 5 systems x 3 trials x 4 candidates = 720 runs)
  - Phase C: Ablation & Pareto Analysis
  - Phase D: 13-Category Failure Diagnosis
  - Phase E: Freezing Final Experiment Manifest
  - Phase F: Generating Research Calibration Report
"""

from __future__ import annotations

import datetime
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from core.logging import get_logger
from experiments.m5.analysis import (
    compute_ablation_deltas,
    compute_system_summary,
)
from experiments.m5.calibrate import CalibrationEvaluator
from experiments.m5.failure_tax import diagnose_trial_failure
from experiments.m5.manifest import ExperimentManifest, SystemID
from experiments.m5.metrics import TrialResult
from experiments.m5.runner import M5BenchmarkRunner
from generation.base import BaseLLMProvider
from generation.providers.factory import build_provider

logger = get_logger(__name__)

RESULTS_DIR = Path("experiments/results/m5")
RAW_DIR = RESULTS_DIR / "raw"
PROCESSED_DIR = RESULTS_DIR / "processed"
CALIBRATION_DIR = RESULTS_DIR / "calibration"
VALIDATION_DIR = RESULTS_DIR / "validation"
DIAGNOSTICS_DIR = RESULTS_DIR / "diagnostics"
FROZEN_DIR = RESULTS_DIR / "frozen"
REPORTS_DIR = RESULTS_DIR / "reports"


class M5CalibrationOrchestrator:
    """
    Executes and coordinates all pre-test calibration and verification steps.
    """

    def __init__(self, llm_provider: Optional[BaseLLMProvider] = None) -> None:
        self.llm_provider = llm_provider or build_provider()

        # Ensure all result directories exist
        for d in (
            RAW_DIR,
            PROCESSED_DIR,
            CALIBRATION_DIR,
            VALIDATION_DIR,
            DIAGNOSTICS_DIR,
            FROZEN_DIR,
            REPORTS_DIR,
        ):
            d.mkdir(parents=True, exist_ok=True)

    def run_phase_a_development(self, trials_count: int = 3) -> Dict[str, Any]:
        """
        Phase A: Execute 24 Dev tasks across all 5 systems with N=3 repeated trials.
        """
        logger.info("==================================================")
        logger.info("PHASE A: Executing Development Split (24 tasks x 5 systems x 3 trials)...")
        logger.info("==================================================")

        runner = M5BenchmarkRunner(
            llm_provider=self.llm_provider,
            raw_output_dir=RAW_DIR,
            processed_output_dir=PROCESSED_DIR,
        )

        dev_summary = runner.run_split(
            split_name="dev",
            trials_count=trials_count,
        )

        # Audit Data Quality across generated raw files
        raw_files = list(RAW_DIR.glob("*_dev.jsonl"))
        total_trials = 0
        data_anomalies: List[str] = []

        for rf in raw_files:
            with open(rf, "r", encoding="utf-8") as f:
                for line_idx, line in enumerate(f):
                    if not line.strip():
                        continue
                    total_trials += 1
                    data = json.loads(line)

                    # Range and consistency checks
                    lat = data.get("latency_ms", 0.0)
                    if lat < 0.0 or lat > 60000.0:
                        data_anomalies.append(f"Invalid latency {lat} in {rf.name}:{line_idx}")

                    tok = data.get("total_tokens", 0)
                    if tok < 0:
                        data_anomalies.append(f"Negative tokens {tok} in {rf.name}:{line_idx}")

                    q = data.get("composite_quality", 0.0)
                    if q < 0.0 or q > 1.0:
                        data_anomalies.append(f"Invalid quality {q} in {rf.name}:{line_idx}")

        logger.info(f"Phase A Complete: {total_trials} trial records audited. Anomalies found: {len(data_anomalies)}.")

        return {
            "dev_summary": dev_summary,
            "total_trial_records": total_trials,
            "data_anomalies": data_anomalies,
        }

    def run_phase_b_validation_calibration(self, trials_count: int = 3) -> Dict[str, Any]:
        """
        Phase B: Execute 12 Validation tasks across 4 candidates x 5 systems x 3 trials.
        """
        logger.info("==================================================")
        logger.info("PHASE B: Executing Validation Calibration (12 tasks x 5 systems x 3 trials x 4 candidates)...")
        logger.info("==================================================")

        evaluator = CalibrationEvaluator(
            llm_provider=self.llm_provider,
            output_dir=CALIBRATION_DIR,
        )

        calib_report = evaluator.run_full_calibration(trials_count=trials_count)

        # Copy winning candidate validation summary to VALIDATION_DIR
        winning_cand_id = calib_report["winning_candidate"]["candidate_id"]
        winning_proc = CALIBRATION_DIR / "processed" / winning_cand_id / "summary_val.json"

        if winning_proc.exists():
            val_dest = VALIDATION_DIR / "summary_val.json"
            val_dest.write_text(winning_proc.read_text(encoding="utf-8"), encoding="utf-8")

        return calib_report

    def run_phase_d_failure_analysis(self) -> Dict[str, Any]:
        """
        Phase D: Execute automated failure taxonomy diagnosis across all raw trial records.
        """
        logger.info("==================================================")
        logger.info("PHASE D: Diagnosing Failure Modes across Trial Records...")
        logger.info("==================================================")

        diagnoses: List[Dict[str, Any]] = []
        counts_by_system: Dict[str, Dict[str, int]] = {}

        raw_files = list(RAW_DIR.glob("*.jsonl")) + list(CALIBRATION_DIR.glob("raw/*/*.jsonl"))

        for rf in raw_files:
            with open(rf, "r", encoding="utf-8") as f:
                for line in f:
                    if not line.strip():
                        continue
                    trial = TrialResult(**json.loads(line))
                    diag = diagnose_trial_failure(trial)
                    diagnoses.append(diag.model_dump())

                    sys_id = trial.system_id
                    counts_by_system.setdefault(sys_id, {})
                    fail_cat = diag.primary_failure
                    counts_by_system[sys_id][fail_cat] = counts_by_system[sys_id].get(fail_cat, 0) + 1

        diag_path = DIAGNOSTICS_DIR / "failure_diagnoses.json"
        with open(diag_path, "w", encoding="utf-8") as f:
            json.dump(
                {
                    "total_diagnoses": len(diagnoses),
                    "summary_by_system": counts_by_system,
                    "diagnoses": diagnoses,
                },
                f,
                indent=2,
            )

        return {
            "total_diagnoses": len(diagnoses),
            "summary_by_system": counts_by_system,
        }

    def run_phase_e_freeze_manifest(
        self, winning_candidate: Dict[str, Any]
    ) -> ExperimentManifest:
        """
        Phase E: Construct and freeze the final experiment manifest.
        """
        logger.info("==================================================")
        logger.info("PHASE E: Freezing Final Experiment Manifest...")
        logger.info("==================================================")

        manifest = ExperimentManifest.create_default()

        # Apply calibrated parameters from winning candidate
        manifest.systems[SystemID.BASELINE_B.value].default_top_k = winning_candidate.get("top_k", 5)
        manifest.systems[SystemID.BASELINE_B.value].default_dense_weight = winning_candidate.get("dense_weight", 0.70)
        manifest.systems[SystemID.BASELINE_B.value].default_sparse_weight = winning_candidate.get("sparse_weight", 0.30)
        manifest.systems[SystemID.SYSTEM_E.value].max_escalations = winning_candidate.get("max_escalations", 2)

        frozen_path = FROZEN_DIR / "final_experiment_manifest.json"
        with open(frozen_path, "w", encoding="utf-8") as f:
            json.dump(manifest.model_dump(), f, indent=2)

        config_hash = manifest.compute_hash()
        logger.info(f"Final Experiment Manifest frozen to {frozen_path} (Hash: {config_hash})")

        return manifest

    def run_phase_f_generate_report(
        self,
        dev_data: Dict[str, Any],
        val_data: Dict[str, Any],
        failure_data: Dict[str, Any],
        frozen_manifest: ExperimentManifest,
    ) -> str:
        """
        Phase F: Generate comprehensive research calibration report in Markdown.
        """
        logger.info("==================================================")
        logger.info("PHASE F: Generating Comprehensive Calibration Report...")
        logger.info("==================================================")

        dev_summary = dev_data["dev_summary"]
        dev_aggs = dev_summary.get("aggregations", {})
        dev_sys_summaries = {
            sys_id: compute_system_summary(task_aggs)
            for sys_id, task_aggs in dev_aggs.items()
        }

        val_aggs = val_data["winning_system_e_performance"]
        winning_cand = val_data["winning_candidate"]
        ablation_deltas = compute_ablation_deltas(dev_sys_summaries)

        report_lines: List[str] = [
            "# Phase-2 M5: Controlled Evaluation Calibration & Validation Report",
            "",
            f"**Generated**: {datetime.datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}  ",
            f"**Frozen Benchmark Version**: `{frozen_manifest.benchmark_version}`  ",
            f"**Frozen Manifest Fingerprint**: `{frozen_manifest.compute_hash()}`  ",
            f"**Split Counts**: Dev = 24 tasks | Validation = 12 tasks | Held-Out Test = 24 tasks (FROZEN)",
            "",
            "> [!IMPORTANT]",
            "> **Research Protocol Constraint Compliance**:",
            "> - The **Held-Out Test Set (24 tasks)** was **NOT** executed, inspected, or utilized during this calibration.",
            "> - All parameter choices were derived strictly from the **Validation Set (12 tasks)**.",
            "> - All findings presented below are **preliminary development/validation results**.",
            "",
            "---",
            "",
            "## 1. Development Experiment Performance (24 Tasks x 5 Systems x 3 Trials = 360 Runs)",
            "",
            "| System Configuration | Quality (0–1) | QC Success Rate | Latency (ms) | Total Energy (J) | Cost ($) | CO2e (g) | Quality / Joule |",
            "|---|---|---|---|---|---|---|---|",
        ]

        for sys_id, s in sorted(dev_sys_summaries.items()):
            report_lines.append(
                f"| `{sys_id}` | {s.get('composite_quality_mean', 0.0):.4f} ± {s.get('composite_quality_std', 0.0):.4f} "
                f"| {s.get('quality_constrained_success_rate', 0.0):.1%} "
                f"| {s.get('latency_ms_mean', 0.0):.1f} ± {s.get('latency_ms_std', 0.0):.1f} "
                f"| {s.get('total_energy_joules_mean', 0.0):.4f} ± {s.get('total_energy_joules_std', 0.0):.4f} "
                f"| ${s.get('cost_usd_mean', 0.0):.6f} "
                f"| {s.get('co2e_grams_mean', 0.0):.6f} "
                f"| {s.get('quality_per_joule_mean', 0.0):.4f} |"
            )

        report_lines.extend([
            "",
            "---",
            "",
            "## 2. Preliminary Stepwise Ablation Deltas (Development Split)",
            "",
            "| Transition | Delta Quality | Delta QC Success | Delta Latency (ms) | Delta Energy (J) | Delta Cost ($) | Delta CO2e (g) |",
            "|---|---|---|---|---|---|---|",
        ])

        for d in ablation_deltas:
            q_s = "+" if d.delta_quality >= 0 else ""
            lat_s = "+" if d.delta_latency_ms >= 0 else ""
            en_s = "+" if d.delta_energy_joules >= 0 else ""
            report_lines.append(
                f"| **{d.transition}** | {q_s}{d.delta_quality:.4f} | — | {lat_s}{d.delta_latency_ms:.1f} "
                f"| {en_s}{d.delta_energy_joules:.4f} | {d.delta_cost_usd:+.6f} | {d.delta_co2e_grams:+.6f} |"
            )

        report_lines.extend([
            "",
            "---",
            "",
            "## 3. Validation Calibration & Parameter Selection (12 Tasks x 4 Candidates)",
            "",
            f"**Winning Configuration**: `{winning_cand['candidate_name']}` (`{winning_cand['candidate_id']}`)",
            "",
            f"**Selection Rationale**: {val_data['selection_rationale']}",
            "",
            "| Candidate ID | Parameters | System E QC Success | System E Quality | System E Energy (J) | Selection Status |",
            "|---|---|---|---|---|---|",
        ])

        for cand_res in val_data["all_candidate_results"]:
            c = cand_res["candidate"]
            perf = cand_res["system_e_performance"]
            status = "⭐ **SELECTED**" if c["candidate_id"] == winning_cand["candidate_id"] else "Alternative"
            param_str = f"top_k={c['top_k']}, hop_depth={c['graph_hop_depth']}, max_esc={c['max_escalations']}"
            report_lines.append(
                f"| `{c['candidate_id']}` | {param_str} | {perf.get('quality_constrained_success_rate', 0.0):.1%} "
                f"| {perf.get('composite_quality_mean', 0.0):.4f} | {perf.get('total_energy_joules_mean', 0.0):.4f} J | {status} |"
            )

        report_lines.extend([
            "",
            "---",
            "",
            "## 4. Failure Mode Taxonomy Summary (13 Standard Categories)",
            "",
            "| System ID | Total Diagnoses | Top Failure Mode | Primary Failure Counts |",
            "|---|---|---|---|",
        ])

        for sys_id, fails in sorted(failure_data["summary_by_system"].items()):
            tot = sum(fails.values())
            top_mode = max(fails.items(), key=lambda kv: kv[1])[0] if fails else "None"
            breakdown = ", ".join(f"{k}: {v}" for k, v in sorted(fails.items(), key=lambda kv: -kv[1])[:3])
            report_lines.append(f"| `{sys_id}` | {tot} | `{top_mode}` | {breakdown} |")

        report_lines.extend([
            "",
            "---",
            "",
            "## 5. Frozen Test Execution Command",
            "",
            "To execute the final benchmark evaluation on the **Held-Out Test Set (24 tasks x 5 systems x 3 trials)**:",
            "",
            "```powershell",
            ".venv311\\Scripts\\python.exe -m experiments.m5.runner --split test --trials 3 --manifest experiments/results/m5/frozen/final_experiment_manifest.json",
            "```",
        ])

        report_text = "\n".join(report_lines)
        report_path = REPORTS_DIR / "m5_calibration_report.md"
        report_path.write_text(report_text, encoding="utf-8")

        logger.info(f"Calibration report generated at {report_path}")
        return report_text

    def execute_all(self, trials_count: int = 3) -> Dict[str, Any]:
        """
        Run the complete pre-test calibration pipeline.
        """
        # Phase A
        dev_res = self.run_phase_a_development(trials_count=trials_count)

        # Phase B
        val_res = self.run_phase_b_validation_calibration(trials_count=trials_count)

        # Phase D
        fail_res = self.run_phase_d_failure_analysis()

        # Phase E
        frozen_manifest = self.run_phase_e_freeze_manifest(val_res["winning_candidate"])

        # Phase F
        report_md = self.run_phase_f_generate_report(
            dev_data=dev_res,
            val_data=val_res,
            failure_data=fail_res,
            frozen_manifest=frozen_manifest,
        )

        return {
            "dev_results": dev_res,
            "validation_results": val_res,
            "failure_results": fail_res,
            "frozen_manifest_hash": frozen_manifest.compute_hash(),
            "report_path": str(REPORTS_DIR / "m5_calibration_report.md"),
        }
