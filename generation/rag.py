"""
Engineering Intelligence Hub — Baseline RAG Generation Pipeline
================================================================
Implements the Phase-1 Baseline RAG pipeline:
Query → Retrieval → Grounded Context Assembly → LLM Prompt → Generation → Sustainability Accounting → Response.

Enforces evidence grounding and explicitly flags INSUFFICIENT EVIDENCE.
"""

from __future__ import annotations

import datetime
import time
from typing import List, Optional

from core.config import settings
from core.logging import get_logger
from experiments.logger import ExperimentLogger
from generation.accounting import account_generation
from generation.base import BaseLLMProvider, GenerationRequest
from generation.providers.factory import build_provider
from knowledge.schemas.tasks import (
    EngTaskRequest,
    EngTaskResponse,
    RetrievedChunk,
    RetrievalResult,
    TaskClassification,
    TaskStatus,
)
from retrieval.base import BaseRetriever
from retrieval.strategies import RetrievalMode, RetrievalStrategyConfig
from sustainability.carbon.estimator import CarbonEstimator
from sustainability.cost.estimator import CostEstimator
from sustainability.energy.estimator import EnergyEstimator

logger = get_logger(__name__)

SYSTEM_PROMPT = """You are an expert Software Engineering AI Assistant within the Engineering Intelligence Hub.
Your task is to answer technical questions and assist with SDLC tasks strictly using the retrieved repository evidence provided below.

Grounding rules:
1. Base your answer ONLY on the provided EVIDENCE. Do NOT invent facts or cite hypothetical files not present in the context.
2. If the retrieved evidence is sufficient, prefix your response with 'SUPPORTED BY EVIDENCE:' and explicitly cite the source file paths and line ranges (e.g. `[src/app.py:L10-L25]`).
3. If the retrieved evidence does NOT contain enough information to answer the question accurately, explicitly state 'INSUFFICIENT EVIDENCE:' followed by what specific information is missing from the repository.
4. Provide precise, production-ready code snippets and explanations when requested.
"""

# System A (LLM only) gets no evidence, so it must not be told to answer only
# from evidence: with SYSTEM_PROMPT it refused every task ("INSUFFICIENT
# EVIDENCE", ~1.5 s), which would make Δ(A→B) measure a strawman instead of the
# contribution of retrieval (PROJECT_REPORT §7.1). Same refusal marker, so
# refusal scoring stays comparable across systems.
NO_RETRIEVAL_SYSTEM_PROMPT = """You are an expert Software Engineering AI Assistant within the Engineering Intelligence Hub.
No repository evidence is available for this question: answer from your own knowledge of the named project and of software engineering.

Rules:
1. Do NOT invent file paths, line numbers or citations; you have no repository evidence to cite.
2. If you do not know the answer reliably, state 'INSUFFICIENT EVIDENCE:' followed by what information you would need.
3. Provide precise, production-ready code snippets and explanations when requested.
"""


class BaselineRAGPipeline:
    """
    End-to-end Baseline RAG generation pipeline.
    """

    def __init__(
        self,
        retriever: Optional[BaseRetriever] = None,
        llm_provider: Optional[BaseLLMProvider] = None,
        model_id: Optional[str] = None,
        energy_estimator: Optional[EnergyEstimator] = None,
        carbon_estimator: Optional[CarbonEstimator] = None,
        cost_estimator: Optional[CostEstimator] = None,
        exp_logger: Optional[ExperimentLogger] = None,
    ) -> None:
        if retriever is not None:
            self.retriever = retriever
        else:
            from retrieval.hybrid import HybridRetriever
            self.retriever = HybridRetriever()

        # No silent mock: the default is the configured real provider (Ollama).
        self.llm_provider = llm_provider or build_provider()

        self.model_id = model_id or settings.model.default_model_id
        # Estimators are built FROM SETTINGS, never bare-constructed: the bare
        # constructors hardcode UK grid intensity and this laptop's TDP values,
        # which would silently misreport energy and CO2e on any other setup.
        self.energy_estimator = energy_estimator or EnergyEstimator.from_settings()
        self.carbon_estimator = carbon_estimator or CarbonEstimator.from_settings()
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

            parts.append(
                f"--- EVIDENCE CHUNK #{i}{repo_str} ---\n"
                f"File: {source_file}{lines_str}{symbol_str}\n"
                f"Content:\n{chunk.content}\n"
            )
        return "\n".join(parts)

    def execute(
        self,
        request: EngTaskRequest,
        strategy: Optional[RetrievalStrategyConfig] = None,
        classification: Optional[TaskClassification] = None,
        skip_retrieval: bool = False,
    ) -> EngTaskResponse:
        """
        Execute the RAG pipeline for an engineering request.
        """
        start_time = time.perf_counter()

        # 1. Strategy setup
        if strategy is None:
            strategy = RetrievalStrategyConfig(
                strategy_name="hybrid",
                mode=RetrievalMode.HYBRID,
                top_k=settings.retrieval.default_top_k,
                repository_filter=request.repository,
            )

        # 2. Retrieval step
        retrieval_result: Optional[RetrievalResult] = None
        context_str = ""
        if not skip_retrieval:
            retrieval_result = self.retriever.retrieve(
                query=request.query,
                strategy=strategy,
                classification=classification,
                task_id=request.task_id,
            )
            context_str = self._build_context_prompt(retrieval_result.chunks)

        # 3. Prompt construction
        if skip_retrieval:
            system_prompt = NO_RETRIEVAL_SYSTEM_PROMPT
            user_prompt = (
                f"ENGINEERING QUESTION / TASK:\n{request.query}\n\n"
                f"Please answer from your own knowledge following the rules."
            )
        else:
            system_prompt = SYSTEM_PROMPT
            user_prompt = (
                f"ENGINEERING QUESTION / TASK:\n{request.query}\n\n"
                f"RETRIEVED REPOSITORY EVIDENCE:\n{context_str}\n\n"
                f"Please provide your grounded engineering answer following the rules."
            )

        gen_request = GenerationRequest(
            prompt=user_prompt,
            system_prompt=system_prompt,
            model_id=self.model_id,
            max_tokens=settings.model.max_tokens,
            temperature=settings.model.temperature,
        )

        # 4. LLM Generation
        gen_response = self.llm_provider.generate(gen_request)
        total_latency_ms = (time.perf_counter() - start_time) * 1000.0

        # 5. Sustainability metrics computation
        account = account_generation(
            gen_response, self.model_id,
            self.energy_estimator, self.carbon_estimator, self.cost_estimator,
        )

        # Reranking energy (if this strategy reranked) is a real local-GPU cost;
        # it is a single-power-sample estimate, so the total becomes ESTIMATED.
        rerank_energy_j = float((retrieval_result.metadata or {}).get("reranker_energy_joules", 0.0) or 0.0)             if retrieval_result is not None else 0.0
        total_energy_j = account.energy_joules + rerank_energy_j
        total_co2e_g = account.co2e_grams + (rerank_energy_j / 3_600_000.0) * self.carbon_estimator.carbon_intensity

        # 6. Response assembly
        response = EngTaskResponse(
            task_id=request.task_id,
            status=TaskStatus.COMPLETED,
            answer=gen_response.text,
            classification=classification,
            retrieval=retrieval_result,
            model_id=self.model_id,
            input_tokens=gen_response.input_tokens,
            output_tokens=gen_response.output_tokens,
            latency_ms=round(total_latency_ms, 2),
            energy_joules=total_energy_j,
            cost_usd=account.cost_usd,
            co2e_grams=total_co2e_g,
            experiment_id=request.experiment_id,
            created_at=datetime.datetime.utcnow().isoformat(),
            metadata={
                "retrieval_strategy": "none" if skip_retrieval else (strategy.strategy_name if strategy else "none"),
                "system_prompt": "no_retrieval" if skip_retrieval else "evidence_grounded",
                "retrieved_chunk_count": len(retrieval_result.chunks) if retrieval_result else 0,
                "provider": self.llm_provider.provider_name,
                "models_called": [gen_response.model_id or self.model_id],
                "model_digest": (gen_response.extra or {}).get("model_digest"),
                "context_check": (gen_response.extra or {}).get("context_check"),
                **{f"generation_{k}": v for k, v in account.as_metadata().items()},
                "generation_energy_measured_joules": (account.energy_joules
                                                      if account.energy_tier == "MEASURED" else None),
                "rerank_energy_joules": rerank_energy_j,
                "energy_tier": account.energy_tier if rerank_energy_j == 0.0 else "ESTIMATED",
                "gpu_max_temp_c": ((gen_response.extra or {}).get("energy") or {}).get("max_temp_c"),
            },
        )

        # 7. Experiment logging
        if self.exp_logger and request.experiment_id:
            try:
                self.exp_logger.log_result(
                    task_id=request.task_id,
                    model_id=self.model_id,
                    answer=response.answer,
                    latency_ms=response.latency_ms or 0.0,
                    input_tokens=response.input_tokens or 0,
                    output_tokens=response.output_tokens or 0,
                    energy_joules=response.energy_joules or 0.0,
                    cost_usd=response.cost_usd or 0.0,
                    co2e_grams=response.co2e_grams or 0.0,
                    metadata=response.metadata,
                )
            except Exception as e:
                logger.warning(f"Failed to log experiment event: {e}")

        return response
