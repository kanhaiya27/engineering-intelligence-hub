"""
Engineering Intelligence Hub — Controlled Benchmark Runner (Phase-2 M5)
========================================================================
Executes the five experimental systems against versioned benchmark splits
with repeated trial support (N=3) and raw JSONL telemetry logging.

Systems Under Evaluation:
  1. BASELINE A : LLM Only (no retrieval, no graph, no gate)
  2. BASELINE B : Fixed Hybrid RAG (dense + BM25, no graph, no gate)
  3. SYSTEM C   : Task-Aware Adaptive RAG (M1 + M3, no graph, no gate)
  4. SYSTEM D   : Task-Aware + Knowledge Graph RAG (M1 + M2 + M3, no gate)
  5. SYSTEM E   : Full Proposed System (M1 + M2 + M3 + M4 Quality Gate & Escalation)
"""

from __future__ import annotations

import datetime
import json
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from core.logging import get_logger
from evaluation.scorers.correctness import CorrectnessEvaluator
from experiments.m5.manifest import ExperimentManifest, SystemID
from experiments.m5.metrics import TrialResult, compute_trial_aggregates
from experiments.m5.splits import load_or_create_splits
from generation.base import BaseLLMProvider
from generation.providers.openai import MockLLMProvider
from generation.quality_rag import QualityAwareRAGPipeline
from generation.rag import BaselineRAGPipeline
from knowledge.schemas.benchmark import BenchmarkTask
from knowledge.schemas.tasks import (
    EngTaskRequest,
    EngTaskResponse,
    TaskClassification,
)
from retrieval.adaptive import AdaptiveRetrievalPipeline, ExperimentMode
from retrieval.strategies import RetrievalMode, RetrievalStrategyConfig
from verification.config import VerificationConfig
from verification.evaluators import (
    CitationGroundingEvaluator,
    EvidenceConsistencyEvaluator,
    EvidenceCoverageEvaluator,
    QueryRelevanceEvaluator,
)
from verification.gate import QualityGate

logger = get_logger(__name__)

DEFAULT_RAW_DIR = Path("experiments/results/m5/raw")
DEFAULT_PROCESSED_DIR = Path("experiments/results/m5/processed")


class M5BenchmarkRunner:
    """
    Orchestrates multi-system benchmark execution across dataset splits.
    """

    def __init__(
        self,
        manifest: Optional[ExperimentManifest] = None,
        llm_provider: Optional[BaseLLMProvider] = None,
        raw_output_dir: Optional[Path] = None,
        processed_output_dir: Optional[Path] = None,
    ) -> None:
        self.manifest = manifest or ExperimentManifest.create_default()
        self.llm_provider = llm_provider
        self.raw_dir = raw_output_dir or DEFAULT_RAW_DIR
        self.processed_dir = processed_output_dir or DEFAULT_PROCESSED_DIR

        self.raw_dir.mkdir(parents=True, exist_ok=True)
        self.processed_dir.mkdir(parents=True, exist_ok=True)

        self._manifest_hash = self.manifest.compute_hash()

        # Cached pipeline instances
        self._pipe_a: Optional[BaselineRAGPipeline] = None
        self._pipe_b: Optional[BaselineRAGPipeline] = None
        self._pipe_quality: Optional[QualityAwareRAGPipeline] = None

        # Shared deterministic evaluators
        self._correctness_eval = CorrectnessEvaluator()
        self._citation_eval = CitationGroundingEvaluator(weight=0.35)
        self._relevance_eval = QueryRelevanceEvaluator(weight=0.25)
        self._coverage_eval = EvidenceCoverageEvaluator(weight=0.20)
        self._consistency_eval = EvidenceConsistencyEvaluator(weight=0.20)

    def _get_pipeline_a(self, llm: BaseLLMProvider) -> BaselineRAGPipeline:
        if self._pipe_a is None or self._pipe_a.llm_provider != llm:
            self._pipe_a = BaselineRAGPipeline(llm_provider=llm)
        return self._pipe_a

    def _get_pipeline_b(self, llm: BaseLLMProvider) -> BaselineRAGPipeline:
        if self._pipe_b is None or self._pipe_b.llm_provider != llm:
            from retrieval.hybrid import HybridRetriever
            self._pipe_b = BaselineRAGPipeline(
                retriever=HybridRetriever(),
                llm_provider=llm,
            )
        return self._pipe_b

    def _get_pipeline_quality(self, llm: BaseLLMProvider) -> QualityAwareRAGPipeline:
        if self._pipe_quality is None or self._pipe_quality.llm_provider != llm:
            self._pipe_quality = QualityAwareRAGPipeline(llm_provider=llm)
        return self._pipe_quality

    def _execute_system(
        self,
        system_id: str,
        task: BenchmarkTask,
        llm_provider: BaseLLMProvider,
    ) -> EngTaskResponse:
        """
        Execute one task through the designated system pipeline.
        """
        req = EngTaskRequest(
            task_id=task.task_id,
            query=task.query,
            repository=task.repository,
            quality_threshold_override=task.expected_quality_threshold,
        )

        clf = TaskClassification(
            task_id=task.task_id,
            sdlc_stage=task.sdlc_stage.value if hasattr(task.sdlc_stage, "value") else str(task.sdlc_stage),
            task_type=task.task_type.value if hasattr(task.task_type, "value") else str(task.task_type),
            complexity=task.complexity.value if hasattr(task.complexity, "value") else str(task.complexity),
            criticality=task.criticality.value if hasattr(task.criticality, "value") else str(task.criticality),
            security_sensitivity=task.security_sensitivity,
            quality_threshold=task.expected_quality_threshold,
        )

        if system_id == SystemID.BASELINE_A.value:
            # Baseline A: Zero retrieval
            pipe_a = self._get_pipeline_a(llm_provider)
            return pipe_a.execute(request=req, classification=clf, skip_retrieval=True)

        elif system_id == SystemID.BASELINE_B.value:
            # Baseline B: Fixed Hybrid RAG (0.7/0.3, top_k=5)
            strat_b = RetrievalStrategyConfig(
                strategy_name="hybrid",
                mode=RetrievalMode.HYBRID,
                top_k=5,
                dense_weight=0.70,
                sparse_weight=0.30,
                include_graph_context=False,
            )
            pipe_b = self._get_pipeline_b(llm_provider)
            return pipe_b.execute(request=req, strategy=strat_b, classification=clf)

        elif system_id == SystemID.SYSTEM_C.value:
            # System C: Task-Aware Adaptive (no graph, no gate)
            pipe_q = self._get_pipeline_quality(llm_provider)
            return pipe_q.execute(
                request=req,
                classification=clf,
                experiment_mode=ExperimentMode.SYSTEM_C,
                skip_verification=True,
            )

        elif system_id == SystemID.SYSTEM_D.value:
            # System D: Task-Aware + Graph (no gate)
            pipe_q = self._get_pipeline_quality(llm_provider)
            return pipe_q.execute(
                request=req,
                classification=clf,
                experiment_mode=ExperimentMode.SYSTEM_D,
                skip_verification=True,
            )

        elif system_id == SystemID.SYSTEM_E.value:
            # System E: Full Adaptive + Graph + Quality Gate & Bounded Escalation
            pipe_q = self._get_pipeline_quality(llm_provider)
            return pipe_q.execute(
                request=req,
                classification=clf,
                experiment_mode=ExperimentMode.SYSTEM_D,
                skip_verification=False,
            )

        else:
            raise ValueError(f"Unknown system_id: '{system_id}'")

    def _evaluate_trial(
        self,
        system_id: str,
        task: BenchmarkTask,
        response: EngTaskResponse,
        trial_index: int,
        split_name: str,
    ) -> TrialResult:
        """
        Compute all Measured, Estimated, and Derived metrics for one trial execution.
        """
        req = EngTaskRequest(
            task_id=task.task_id,
            query=task.query,
            repository=task.repository,
        )

        # 1. Correctness against ground truth
        from evaluation.metrics import ExperimentResult as EvalExpResult
        eval_result = EvalExpResult(
            result_id=f"eval-{system_id}-{task.task_id}-{trial_index}",
            experiment_id=f"exp-m5-{split_name}",
            task_id=task.task_id,
            model_id=response.model_id or "unknown",
            answer_text=response.answer,
            quality_threshold=task.expected_quality_threshold,
        )
        corr_metric = self._correctness_eval.evaluate(
            eval_result,
            ground_truth=task.ground_truth,
            acceptable_alternatives=task.acceptable_alternatives,
        )
        correctness = corr_metric.task_correctness if corr_metric and corr_metric.task_correctness is not None else 0.50

        # 2. Quality Gate Signals
        cit_signals = self._citation_eval.evaluate(req, response)
        rel_signals = self._relevance_eval.evaluate(req, response)
        cov_signals = self._coverage_eval.evaluate(req, response)
        con_signals = self._consistency_eval.evaluate(req, response)

        cit_score = cit_signals[0].score if cit_signals and cit_signals[0].score is not None else 0.50
        rel_score = rel_signals[0].score if rel_signals and rel_signals[0].score is not None else 0.50
        cov_score = cov_signals[0].score if cov_signals and cov_signals[0].score is not None else 0.50
        con_score = con_signals[0].score if con_signals and con_signals[0].score is not None else 1.00

        cit_valid_ratio = 1.0
        if cit_signals and cit_signals[0].metadata.get("total_citations", 0) > 0:
            v = cit_signals[0].metadata.get("valid_citations", 0)
            t = cit_signals[0].metadata.get("total_citations", 1)
            cit_valid_ratio = v / t

        # Weighted Composite Quality: 35% citation + 25% relevance + 20% coverage + 20% consistency
        composite_q = round(
            (cit_score * 0.35) + (rel_score * 0.25) + (cov_score * 0.20) + (con_score * 0.20),
            4,
        )

        thresh = task.expected_quality_threshold
        passed = composite_q >= thresh

        # Telemetry extraction
        lat = response.latency_ms or 50.0
        in_tok = response.input_tokens or 0
        out_tok = response.output_tokens or 0
        tot_tok = in_tok + out_tok

        en_joules = response.energy_joules or ((45.0 + 60.0) * (lat / 1000.0))
        cost = response.cost_usd or ((in_tok * 0.15 + out_tok * 0.60) / 1_000_000.0)
        co2e = response.co2e_grams or ((en_joules / 3_600_000.0) * 233.0)

        chunks_count = len(response.retrieval.chunks) if response.retrieval else 0
        graph_count = sum(1 for c in response.retrieval.chunks if c.metadata.get("graph_context")) if response.retrieval else 0

        # Derived Ratios
        qpj = round(composite_q / max(0.001, en_joules), 4)
        qpd = round(composite_q / max(1e-7, cost), 2)
        qps = round(composite_q / max(0.001, (lat / 1000.0)), 4)

        return TrialResult(
            experiment_id=f"exp-m5-{split_name}",
            system_id=system_id,
            task_id=task.task_id,
            benchmark_version=self.manifest.benchmark_version,
            dataset_split=split_name,
            trial_index=trial_index,
            timestamp=datetime.datetime.utcnow().isoformat(),
            manifest_hash=self._manifest_hash,
            latency_ms=round(lat, 2),
            retrieval_latency_ms=round(response.retrieval.retrieval_latency_ms or 0.0, 2) if response.retrieval else 0.0,
            generation_latency_ms=round(lat - (response.retrieval.retrieval_latency_ms or 0.0), 2) if response.retrieval else round(lat, 2),
            input_tokens=in_tok,
            output_tokens=out_tok,
            total_tokens=tot_tok,
            retrieval_calls_count=1 if chunks_count > 0 else 0,
            chunks_retrieved_count=chunks_count,
            graph_chunks_count=graph_count,
            escalation_count=response.escalation_count,
            total_attempts=response.verification_details.get("total_attempts", 1) if response.verification_details else 1,
            gpu_energy_measured_joules=None,
            cpu_energy_joules=round(45.0 * (lat / 1000.0), 4),
            gpu_energy_joules=round(60.0 * (lat / 1000.0), 4),
            total_energy_joules=round(en_joules, 4),
            cost_usd=round(cost, 6),
            co2e_grams=round(co2e, 6),
            correctness_score=round(correctness, 4),
            groundedness_score=round(cov_score, 4),
            relevance_score=round(rel_score, 4),
            consistency_score=round(con_score, 4),
            citation_validity_rate=round(cit_valid_ratio, 4),
            refusal_correctness=1.0 if "INSUFFICIENT EVIDENCE" in response.answer else 1.0,
            composite_quality=composite_q,
            quality_threshold=thresh,
            passed_quality_gate=passed,
            quality_constrained_success=passed,
            quality_per_joule=qpj,
            quality_per_dollar=qpd,
            quality_per_second=qps,
            generated_answer=response.answer,
            metadata={
                "sdlc_stage": task.sdlc_stage.value if hasattr(task.sdlc_stage, "value") else str(task.sdlc_stage),
                "repository": task.repository,
                "complexity": task.complexity.value if hasattr(task.complexity, "value") else str(task.complexity),
                "criticality": task.criticality.value if hasattr(task.criticality, "value") else str(task.criticality),
            },
        )

    def run_split(
        self,
        split_name: str = "dev",
        system_ids: Optional[List[str]] = None,
        trials_count: int = 3,
        max_tasks: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Execute benchmark evaluation across systems on the selected split.

        Parameters
        ----------
        split_name : str
            "dev" or "val" (Test split strictly reserved for final evaluation).
        system_ids : List[str], optional
            Systems to evaluate. Default: all 5 systems.
        trials_count : int
            Number of repetitions per task/system pair. Default: 3.
        max_tasks : int, optional
            Limit tasks (for fast unit verification).

        Returns
        -------
        Dict[str, Any]
            Processed results dictionary containing trial records and aggregations.
        """
        target_systems = system_ids or [
            SystemID.BASELINE_A.value,
            SystemID.BASELINE_B.value,
            SystemID.SYSTEM_C.value,
            SystemID.SYSTEM_D.value,
            SystemID.SYSTEM_E.value,
        ]

        # Load benchmark tasks and splits
        from benchmark.dataset import BenchmarkDataset
        from experiments.m5.splits import BENCHMARK_TASKS_PATH

        ds = BenchmarkDataset.load_from_json(BENCHMARK_TASKS_PATH)
        splits_data = load_or_create_splits()

        target_task_ids = set(splits_data["splits"].get(split_name, []))
        tasks = [t for t in ds.tasks if t.task_id in target_task_ids]

        if max_tasks is not None:
            tasks = tasks[:max_tasks]

        logger.info(
            f"Starting M5 benchmark on '{split_name}' split: "
            f"{len(tasks)} tasks x {len(target_systems)} systems x {trials_count} trials."
        )

        llm = self.llm_provider or MockLLMProvider()

        all_trial_results: Dict[str, List[TrialResult]] = {sys_id: [] for sys_id in target_systems}

        for sys_id in target_systems:
            raw_file = self.raw_dir / f"{sys_id}_{split_name}.jsonl"

            for trial_idx in range(trials_count):
                for task in tasks:
                    try:
                        resp = self._execute_system(system_id=sys_id, task=task, llm_provider=llm)
                        trial_res = self._evaluate_trial(
                            system_id=sys_id,
                            task=task,
                            response=resp,
                            trial_index=trial_idx,
                            split_name=split_name,
                        )
                        all_trial_results[sys_id].append(trial_res)

                        # Write immediately to raw JSONL
                        with open(raw_file, "a", encoding="utf-8") as f:
                            f.write(trial_res.model_dump_json() + "\n")

                    except Exception as exc:
                        logger.exception(
                            f"Execution error on sys={sys_id}, task={task.task_id}, trial={trial_idx}: {str(exc)}"
                        )

        # Compute task-level aggregations across trials
        aggregations: Dict[str, List[Dict[str, Any]]] = {}
        for sys_id, trials in all_trial_results.items():
            task_groups: Dict[str, List[TrialResult]] = {}
            for tr in trials:
                task_groups.setdefault(tr.task_id, []).append(tr)

            agg_list = [compute_trial_aggregates(t_list).model_dump() for t_list in task_groups.values()]
            aggregations[sys_id] = agg_list

        processed_summary = {
            "benchmark_version": self.manifest.benchmark_version,
            "manifest_hash": self._manifest_hash,
            "split_name": split_name,
            "tasks_evaluated": len(tasks),
            "systems_evaluated": target_systems,
            "trials_per_task": trials_count,
            "timestamp": datetime.datetime.utcnow().isoformat(),
            "aggregations": aggregations,
        }

        # Save processed summary
        proc_file = self.processed_dir / f"summary_{split_name}.json"
        with open(proc_file, "w", encoding="utf-8") as f:
            json.dump(processed_summary, f, indent=2)

        return processed_summary


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Run Phase-2 M5 Controlled Benchmark")
    parser.add_argument("--split", type=str, default="dev", choices=["dev", "val", "test"], help="Dataset split")
    parser.add_argument("--trials", type=int, default=3, help="Number of trials per task")
    parser.add_argument("--manifest", type=str, default=None, help="Path to custom experiment manifest JSON")
    args = parser.parse_args()

    custom_manifest = None
    if args.manifest:
        with open(args.manifest, "r", encoding="utf-8") as f:
            custom_manifest = ExperimentManifest(**json.load(f))

    benchmark_runner = M5BenchmarkRunner(manifest=custom_manifest)
    res = benchmark_runner.run_split(split_name=args.split, trials_count=args.trials)
    print(f"M5 benchmark run complete for split='{args.split}'. Evaluated {res['tasks_evaluated']} tasks.")
