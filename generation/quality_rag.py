"""
Engineering Intelligence Hub — Quality-Aware RAG Pipeline (Phase-2 M4)
======================================================================
Implements quality-gated engineering RAG with bounded escalation.

Loop:
  Query → Adaptive Retrieval (M3)
      → LLM Generation
      → Quality-Aware Verification (M4)
      → If PASS: Return EngTaskResponse
      → If FAIL and attempts < max_escalations:
            EscalationPolicy → Stronger Retrieval → Regenerate → Verify again
      → If escalations exhausted:
            Return EngTaskResponse with explicit INSUFFICIENT EVIDENCE refusal.

Preserves full provenance and telemetry across all attempts for M5 analysis.
BaselineRAGPipeline is UNCHANGED.
"""

from __future__ import annotations

import datetime
import time
from typing import Any, Dict, List, Optional

from core.config import settings
from core.logging import get_logger
from experiments.logger import ExperimentLogger
from generation.base import BaseLLMProvider, GenerationRequest
from generation.providers.openai import MockLLMProvider, OpenAIProvider
from generation.rag import SYSTEM_PROMPT
from knowledge.schemas.tasks import (
    EngTaskRequest,
    EngTaskResponse,
    RetrievalResult,
    RetrievedChunk,
    TaskClassification,
    TaskStatus,
)
from retrieval.adaptive import AdaptiveRetrievalPipeline, ExperimentMode
from retrieval.base import BaseRetriever
from retrieval.strategies import RetrievalMode, RetrievalStrategyConfig
from sustainability.carbon.estimator import CarbonEstimator
from sustainability.cost.estimator import CostEstimator
from sustainability.energy.estimator import EnergyEstimator
from verification.config import VerificationConfig
from verification.escalation import EscalationPolicy
from verification.gate import QualityGate
from verification.signals import QualityReport

logger = get_logger(__name__)


class QualityAwareRAGPipeline:
    """
    Quality-gated adaptive RAG pipeline with bounded escalation support.
    """

    def __init__(
        self,
        adaptive_pipeline: Optional[AdaptiveRetrievalPipeline] = None,
        retriever: Optional[BaseRetriever] = None,
        llm_provider: Optional[BaseLLMProvider] = None,
        quality_gate: Optional[QualityGate] = None,
        escalation_policy: Optional[EscalationPolicy] = None,
        verification_config: Optional[VerificationConfig] = None,
        model_id: Optional[str] = None,
        energy_estimator: Optional[EnergyEstimator] = None,
        carbon_estimator: Optional[CarbonEstimator] = None,
        cost_estimator: Optional[CostEstimator] = None,
        exp_logger: Optional[ExperimentLogger] = None,
    ) -> None:
        self.adaptive_pipeline = adaptive_pipeline or AdaptiveRetrievalPipeline()
        self.fallback_retriever = retriever

        if llm_provider:
            self.llm_provider = llm_provider
        elif settings.secrets.openai_api_key:
            self.llm_provider = OpenAIProvider()
        else:
            self.llm_provider = MockLLMProvider()

        self.verification_config = verification_config or VerificationConfig()
        self.quality_gate = quality_gate or QualityGate.default_gate(self.verification_config)
        self.escalation_policy = escalation_policy or EscalationPolicy(self.verification_config)

        self.model_id = model_id or settings.model.default_model_id
        self.energy_estimator = energy_estimator or EnergyEstimator()
        self.carbon_estimator = carbon_estimator or CarbonEstimator()
        self.cost_estimator = cost_estimator or CostEstimator()
        self.exp_logger = exp_logger

    def _build_context_prompt(self, chunks: List[RetrievedChunk]) -> str:
        """Format retrieved chunks with clear provenance headers."""
        if not chunks:
            return "NO EVIDENCE RETRIEVED."

        parts = []
        for i, chunk in enumerate(chunks, start=1):
            source_file = chunk.source_path or "unknown_file"
            lines_str = ""
            start_l = chunk.metadata.get("start_line")
            end_l = chunk.metadata.get("end_line")
            if start_l is not None and end_l is not None:
                lines_str = f" (Lines {start_l}-{end_l})"

            repo_str = f" [{chunk.repository}]" if chunk.repository else ""
            symbol_str = f" | Symbol: {chunk.metadata.get('symbol_name')}" if chunk.metadata.get("symbol_name") else ""
            is_graph_ctx = " [GRAPH CONTEXT]" if chunk.metadata.get("graph_context") else ""

            parts.append(
                f"--- EVIDENCE CHUNK #{i}{repo_str}{is_graph_ctx} ---\n"
                f"File: {source_file}{lines_str}{symbol_str}\n"
                f"Content:\n{chunk.content}\n"
            )
        return "\n".join(parts)

    def execute(
        self,
        request: EngTaskRequest,
        classification: Optional[TaskClassification] = None,
        initial_strategy: Optional[RetrievalStrategyConfig] = None,
        experiment_mode: ExperimentMode = ExperimentMode.SYSTEM_D,
        skip_verification: bool = False,
    ) -> EngTaskResponse:
        """
        Execute the quality-aware RAG pipeline with verification and bounded escalation.

        Parameters
        ----------
        request : EngTaskRequest
            The incoming engineering request.
        classification : TaskClassification, optional
            M1 classification output (contains task-specific quality_threshold).
        initial_strategy : RetrievalStrategyConfig, optional
            Override initial retrieval strategy.
        experiment_mode : ExperimentMode
            Controls retrieval behavior (BASELINE_B, SYSTEM_C, SYSTEM_D).
        skip_verification : bool
            If True, skips the quality gate (e.g. for ablation baseline comparison).

        Returns
        -------
        EngTaskResponse
            Response with full quality, retrieval, sustainability, and escalation telemetry.
        """
        pipeline_start_time = time.perf_counter()

        # 1. Resolve quality threshold (task-specific from M1 -> override -> config default)
        threshold = (
            request.quality_threshold_override
            if request.quality_threshold_override is not None
            else (
                classification.quality_threshold
                if classification and classification.quality_threshold is not None
                else self.verification_config.default_quality_threshold
            )
        )

        max_escalations = self.escalation_policy.get_max_attempts()

        # Accumulated metrics across all attempts
        total_input_tokens = 0
        total_output_tokens = 0
        total_energy_joules = 0.0
        total_cost_usd = 0.0
        total_co2e_grams = 0.0
        attempt_history: List[Dict[str, Any]] = []

        current_strategy = initial_strategy
        current_attempt = 0
        final_response: Optional[EngTaskResponse] = None
        final_report: Optional[QualityReport] = None
        passed_gate = False

        while current_attempt <= max_escalations:
            attempt_start_time = time.perf_counter()

            # --- A. Retrieval Step ---
            retrieval_result: Optional[RetrievalResult] = None
            if current_strategy is not None:
                # Use current_strategy override
                retrieval_result = self.adaptive_pipeline.retrieve(
                    query=request.query,
                    classification=classification or TaskClassification(
                        task_id=request.task_id,
                        sdlc_stage=request.sdlc_stage_hint or "unknown",
                        task_type=request.task_type_hint or "unknown",
                        complexity="medium",
                        criticality="medium",
                        security_sensitivity="none",
                        quality_threshold=threshold,
                    ),
                    experiment_mode=experiment_mode,
                    override_strategy_name=current_strategy.strategy_name,
                    task_id=request.task_id,
                )
            else:
                # Resolve via adaptive policy on attempt 0
                if classification:
                    retrieval_result = self.adaptive_pipeline.retrieve(
                        query=request.query,
                        classification=classification,
                        experiment_mode=experiment_mode,
                        task_id=request.task_id,
                    )
                    current_strategy = self.adaptive_pipeline.list_strategies().get(
                        retrieval_result.strategy_used,
                        RetrievalStrategyConfig(strategy_name=retrieval_result.strategy_used),
                    )
                else:
                    # Default hybrid strategy
                    current_strategy = RetrievalStrategyConfig(
                        strategy_name="hybrid",
                        mode=RetrievalMode.HYBRID,
                        top_k=settings.retrieval.default_top_k,
                        repository_filter=request.repository,
                    )
                    retrieval_result = self.adaptive_pipeline.retrieve(
                        query=request.query,
                        classification=TaskClassification(
                            task_id=request.task_id,
                            sdlc_stage="unknown",
                            task_type="unknown",
                            complexity="medium",
                            criticality="medium",
                            security_sensitivity="none",
                            quality_threshold=threshold,
                        ),
                        experiment_mode=experiment_mode,
                        override_strategy_name="hybrid",
                        task_id=request.task_id,
                    )

            # --- B. Prompt & Generation ---
            context_str = self._build_context_prompt(retrieval_result.chunks)
            user_prompt = (
                f"ENGINEERING QUESTION / TASK:\n{request.query}\n\n"
                f"RETRIEVED REPOSITORY EVIDENCE:\n{context_str}\n\n"
                f"Please provide your grounded engineering answer following the rules."
            )

            gen_request = GenerationRequest(
                prompt=user_prompt,
                system_prompt=SYSTEM_PROMPT,
                model_id=self.model_id,
                max_tokens=settings.model.max_tokens,
                temperature=settings.model.temperature,
            )

            gen_response = self.llm_provider.generate(gen_request)

            # --- C. Telemetry Accounting for this attempt ---
            attempt_input_tokens = gen_response.input_tokens or 0
            attempt_output_tokens = gen_response.output_tokens or 0
            total_input_tokens += attempt_input_tokens
            total_output_tokens += attempt_output_tokens

            energy_est = self.energy_estimator.estimate(
                latency_ms=gen_response.latency_ms,
                input_tokens=attempt_input_tokens,
                output_tokens=attempt_output_tokens,
                model_id=self.model_id,
                is_local_model=False,
            )
            cost_est = self.cost_estimator.estimate(
                input_tokens=attempt_input_tokens,
                output_tokens=attempt_output_tokens,
                model_id=self.model_id,
            )
            carbon_est = self.carbon_estimator.estimate(energy_estimate=energy_est)

            total_energy_joules += energy_est.energy_joules
            total_cost_usd += cost_est.total_cost_usd
            total_co2e_grams += carbon_est.co2e_grams

            attempt_latency_ms = (time.perf_counter() - attempt_start_time) * 1000.0

            # Formulate candidate response
            candidate_response = EngTaskResponse(
                task_id=request.task_id,
                status=TaskStatus.COMPLETED,
                answer=gen_response.text,
                classification=classification,
                retrieval=retrieval_result,
                model_id=self.model_id,
                input_tokens=attempt_input_tokens,
                output_tokens=attempt_output_tokens,
                latency_ms=round(attempt_latency_ms, 2),
                energy_joules=energy_est.energy_joules,
                cost_usd=cost_est.total_cost_usd,
                co2e_grams=carbon_est.co2e_grams,
                experiment_id=request.experiment_id,
                created_at=datetime.datetime.utcnow().isoformat(),
            )

            # --- D. Quality Verification Step ---
            if skip_verification:
                final_response = candidate_response
                passed_gate = True
                break

            from core.exceptions import EscalationExhaustedError

            try:
                report = self.quality_gate.check(
                    request=request,
                    response=candidate_response,
                    threshold=threshold,
                    attempt=current_attempt,
                )
            except EscalationExhaustedError:
                # Re-compute report to capture signals without raising
                report = QualityReport.compute(
                    task_id=request.task_id,
                    signals=[
                        sig
                        for evaluator in self.quality_gate.evaluators
                        for sig in evaluator.evaluate(request, candidate_response)
                    ],
                    threshold=threshold,
                    model_id=candidate_response.model_id,
                )

            final_report = report

            # Record attempt telemetry
            attempt_record = {
                "attempt_number": current_attempt,
                "strategy_used": current_strategy.strategy_name if current_strategy else "none",
                "chunks_retrieved": len(retrieval_result.chunks),
                "quality_score": report.aggregated_score,
                "threshold": threshold,
                "passed": report.passed,
                "critical_failures": report.critical_failures,
                "signals": [
                    {
                        "signal_type": s.signal_type,
                        "status": s.status,
                        "score": s.score,
                        "weight": s.weight,
                        "rationale": s.rationale,
                    }
                    for s in report.signals
                ],
                "attempt_latency_ms": round(attempt_latency_ms, 2),
                "attempt_input_tokens": attempt_input_tokens,
                "attempt_output_tokens": attempt_output_tokens,
            }
            attempt_history.append(attempt_record)

            if report.passed:
                final_response = candidate_response
                passed_gate = True
                logger.info(
                    f"Task {request.task_id}: Quality gate PASSED on attempt {current_attempt} "
                    f"(score={report.aggregated_score:.3f} >= threshold={threshold:.2f})"
                )
                break
            else:
                logger.warning(
                    f"Task {request.task_id}: Quality gate FAILED on attempt {current_attempt} "
                    f"(score={report.aggregated_score} < threshold={threshold:.2f})"
                )
                if current_attempt < max_escalations:
                    # --- E. Escalation Step ---
                    current_attempt += 1
                    current_strategy = self.escalation_policy.escalate(
                        current_strategy=current_strategy,
                        attempt=current_attempt,
                        report=report,
                    )
                else:
                    # Escalations exhausted — break to insufficient evidence handler
                    current_attempt += 1
                    break

        total_latency_ms = (time.perf_counter() - pipeline_start_time) * 1000.0

        # --- F. Assembly of Final Response ---
        if not passed_gate and not skip_verification:
            # Fallback to explicit refusal when all escalations fail
            refusal_answer = (
                f"INSUFFICIENT EVIDENCE: The retrieved repository evidence across "
                f"{len(attempt_history)} retrieval attempt(s) does not contain sufficient "
                f"verifiable information to accurately answer: '{request.query}'. "
                f"Required quality threshold: {threshold:.2f}, best score achieved: "
                f"{final_report.aggregated_score if final_report else 'N/A'}."
            )
            final_response = EngTaskResponse(
                task_id=request.task_id,
                status=TaskStatus.COMPLETED,
                answer=refusal_answer,
                classification=classification,
                retrieval=candidate_response.retrieval if 'candidate_response' in locals() else None,
                model_id=self.model_id,
                input_tokens=total_input_tokens,
                output_tokens=total_output_tokens,
                latency_ms=round(total_latency_ms, 2),
                energy_joules=round(total_energy_joules, 6),
                cost_usd=round(total_cost_usd, 6),
                co2e_grams=round(total_co2e_grams, 6),
                experiment_id=request.experiment_id,
                created_at=datetime.datetime.utcnow().isoformat(),
            )

        # Populate top-level verification fields on the response
        final_response.quality_score = final_report.aggregated_score if final_report else None
        final_response.quality_threshold_used = threshold
        final_response.passed_quality_gate = passed_gate
        final_response.escalation_count = max(0, len(attempt_history) - 1)
        final_response.latency_ms = round(total_latency_ms, 2)
        final_response.input_tokens = total_input_tokens
        final_response.output_tokens = total_output_tokens
        final_response.energy_joules = round(total_energy_joules, 6)
        final_response.cost_usd = round(total_cost_usd, 6)
        final_response.co2e_grams = round(total_co2e_grams, 6)

        final_response.verification_details = {
            "passed_quality_gate": passed_gate,
            "quality_score": final_report.aggregated_score if final_report else None,
            "threshold_applied": threshold,
            "total_attempts": len(attempt_history),
            "escalation_count": max(0, len(attempt_history) - 1),
            "final_report": final_report.model_dump() if final_report else None,
            "attempt_history": attempt_history,
        }

        final_response.metadata.update({
            "experiment_mode": experiment_mode.value if hasattr(experiment_mode, "value") else str(experiment_mode),
            "total_attempts": len(attempt_history),
            "provider": self.llm_provider.provider_name,
        })

        # --- G. Experiment Logging ---
        if self.exp_logger and request.experiment_id:
            try:
                self.exp_logger.log_result(
                    task_id=request.task_id,
                    model_id=self.model_id,
                    answer=final_response.answer,
                    latency_ms=final_response.latency_ms or 0.0,
                    input_tokens=final_response.input_tokens or 0,
                    output_tokens=final_response.output_tokens or 0,
                    energy_joules=final_response.energy_joules or 0.0,
                    cost_usd=final_response.cost_usd or 0.0,
                    co2e_grams=final_response.co2e_grams or 0.0,
                    metadata=final_response.metadata,
                )
            except Exception as e:
                logger.warning(f"Failed to log experiment event: {e}")

        return final_response
