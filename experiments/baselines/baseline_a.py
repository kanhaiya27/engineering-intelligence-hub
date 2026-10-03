"""
Engineering Intelligence Hub — Baseline A Runner (LLM Only)
============================================================
Executes experimental Baseline A: LLM-only generation with ZERO repository retrieval.
Establishes the performance floor for knowledge grounding, latency, cost, and energy.
"""

from __future__ import annotations

import datetime
from typing import List, Optional

from core.logging import get_logger
from evaluation.metrics import (
    EfficiencyMetrics,
    EngineeringOutcomeMetrics,
    ExperimentResult,
)
from evaluation.suite import BaselineEvaluatorSuite
from experiments.config import ExperimentConfig
from experiments.logger import ExperimentLogger
from experiments.runner import BaseExperimentRunner
from generation.rag import BaselineRAGPipeline
from knowledge.schemas.benchmark import BenchmarkTask
from knowledge.schemas.tasks import EngTaskRequest

logger = get_logger(__name__)


class BaselineARunner(BaseExperimentRunner):
    """
    Runner for Baseline A (LLM Only, No RAG).
    """

    def __init__(
        self,
        config: ExperimentConfig,
        exp_logger: ExperimentLogger,
        tasks: List[BenchmarkTask],
        rag_pipeline: Optional[BaselineRAGPipeline] = None,
        evaluator_suite: Optional[BaselineEvaluatorSuite] = None,
    ) -> None:
        super().__init__(config, exp_logger)
        self.tasks = tasks
        self.rag_pipeline = rag_pipeline or BaselineRAGPipeline()
        self.evaluator_suite = evaluator_suite or BaselineEvaluatorSuite()

    @property
    def runner_name(self) -> str:
        return "baseline_a_llm_only"

    def run(self) -> List[ExperimentResult]:
        """Execute Baseline A over all tasks."""
        self.setup()
        self.exp_logger.log_experiment_start()
        self.exp_logger.log_config(self.config.model_dump())

        results: List[ExperimentResult] = []
        successful_count = 0

        logger.info(f"Starting Baseline A ({len(self.tasks)} tasks, model={self.config.model_id})...")

        for idx, task in enumerate(self.tasks, start=1):
            req = EngTaskRequest(
                task_id=task.task_id,
                query=task.query,
                repository=task.repository,
                experiment_id=self.config.experiment_id,
            )

            # 1. Execute LLM without retrieval
            resp = self.rag_pipeline.execute(
                request=req,
                skip_retrieval=True,
            )

            # 2. Build preliminary result
            exp_result = ExperimentResult(
                result_id=f"{self.config.experiment_id}_{task.task_id}_{idx}",
                experiment_id=self.config.experiment_id,
                task_id=task.task_id,
                run_index=idx,
                created_at=datetime.datetime.utcnow().isoformat(),
                experiment_config_name=self.config.experiment_name,
                model_id=self.config.model_id,
                retrieval_strategy="none",
                quality_threshold=task.expected_quality_threshold,
                answer_text=resp.answer,
            )

            # 3. Evaluate quality
            q_metrics = self.evaluator_suite.evaluate(
                result=exp_result,
                query=task.query,
                ground_truth=task.ground_truth,
                acceptable_alternatives=task.acceptable_alternatives,
                context_chunks_text=None,
            )
            exp_result.quality = q_metrics

            # 4. Compute efficiency metrics
            exp_result.efficiency = EfficiencyMetrics(
                task_id=task.task_id,
                latency_ms=resp.latency_ms,
                input_tokens=resp.input_tokens,
                output_tokens=resp.output_tokens,
                total_tokens=(resp.input_tokens or 0) + (resp.output_tokens or 0),
                cost_usd=resp.cost_usd,
                energy_joules=resp.energy_joules,
                energy_estimation_method="tdp_proxy",
                co2e_grams=resp.co2e_grams,
                num_chunks_retrieved=0,
                retrieval_latency_ms=0.0,
                retrieval_strategy="none",
                model_id=self.config.model_id,
            )

            # 5. Outcome metrics
            is_successful = bool(q_metrics.passed_quality_gate)
            if is_successful:
                successful_count += 1

            exp_result.outcome = EngineeringOutcomeMetrics(
                task_id=task.task_id,
                task_completed=is_successful,
            )

            # 6. Log result
            self.exp_logger.log_result(exp_result.model_dump())
            results.append(exp_result)

        self.exp_logger.log_experiment_end(
            total_tasks=len(self.tasks),
            successful_tasks=successful_count,
        )
        self.teardown()

        logger.info(f"Baseline A complete: {successful_count}/{len(self.tasks)} passed quality gate.")
        return results
