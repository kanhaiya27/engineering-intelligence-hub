"""
Illustrative v1 trace payloads for docs and contract tests.

Every number here is a hand-written PLACEHOLDER chosen to show the shape of the
contract. None of it comes from a run, and every example is marked
``generation_source="mock"``, ``research_evidence=False`` and carries
``ILLUSTRATIVE_WARNING`` so it can never be mistaken for a result.

    python -m apps.api.contract.examples   # rewrite docs/api/examples/*.json
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from apps.api.contract.v1 import (
    AttemptTrace,
    ChannelExecution,
    ClassificationTrace,
    EscalationStep,
    EscalationSummary,
    ExecutionContext,
    GenerationTrace,
    GraphExecution,
    MachineInfo,
    Metric,
    Outcome,
    ParameterChange,
    PipelineTrace,
    Provenance,
    RerankerExecution,
    ResourceMetrics,
    RetrievalTrace,
    RetrievedChunkTrace,
    SignalTrace,
    SystemId,
    Verdict,
    VerificationTrace,
)

ILLUSTRATIVE_WARNING = (
    "ILLUSTRATIVE EXAMPLE: hand-written placeholder values, not results of any run."
)

EXAMPLES_DIR = Path(__file__).resolve().parents[3] / "docs" / "api" / "examples"

_CREATED_AT = datetime(2026, 10, 5, tzinfo=timezone.utc)


def _m(value, unit, provenance: Provenance, method: str) -> Metric:
    return Metric(value=value, unit=unit, provenance=provenance, method=method)


def _na(unit) -> Metric:
    return Metric(value=None, unit=unit, provenance=None, method="not_available")


def _resources(scale: int = 1) -> ResourceMetrics:
    """Placeholder resources for one mock attempt (API-style model: no GPU, no cost table)."""
    return ResourceMetrics(
        latency_ms=_m(100 * scale, "ms", Provenance.MEASURED, "perf_counter"),
        input_tokens=_m(1000 * scale, "tokens", Provenance.MEASURED, "provider_usage"),
        output_tokens=_m(100 * scale, "tokens", Provenance.MEASURED, "provider_usage"),
        cost_usd=_na("usd"),
        energy_joules=_m(1.0 * scale, "joules", Provenance.ESTIMATED, "sum"),
        energy_cpu_joules=_m(1.0 * scale, "joules", Provenance.ESTIMATED, "tdp_proxy"),
        energy_gpu_joules=Metric(
            value=None,
            unit="joules",
            provenance=None,
            method="not_available",
            note="remote API model: GPU energy is outside the system boundary",
        ),
        energy_rerank_joules=_m(0, "joules", Provenance.DERIVED, "not_executed"),
        co2e_grams=_m(0.0002 * scale, "gco2e", Provenance.ESTIMATED, "grid_intensity"),
    )


def _chunk(rank: int, channel: str = "hybrid", graph_hop: Optional[int] = None) -> RetrievedChunkTrace:
    path = f"src/example/module_{rank}.py"
    return RetrievedChunkTrace(
        rank=rank,
        chunk_id=f"example/repo:{path}:0000000000000000:chunk:0",
        channel=channel,
        repository="example/repo",
        file_path=path,
        start_line=10,
        end_line=20,
        symbol_name=f"example_function_{rank}",
        commit_sha="0000000",
        citation=f"example/repo:{path}:10-20",
        score=1.0 / rank,
        score_kind="graph" if channel == "graph" else "fused",
        dense_score=None if channel == "graph" else 1.0 / rank,
        sparse_score=None if channel == "graph" else 1.0 / rank,
        graph_hop=graph_hop,
        content="def example_function():\n    ...  # placeholder content\n",
        content_truncated=False,
    )


def _retrieval(attempt: int, graph: bool) -> RetrievalTrace:
    chunks = [_chunk(1), _chunk(2)]
    if graph:
        chunks.append(_chunk(3, channel="graph", graph_hop=1))
    strategy = "hybrid_balanced" if attempt == 0 else "hybrid_balanced_esc1"
    return RetrievalTrace(
        attempt_index=attempt,
        requested_strategy=strategy,
        strategy_name=strategy,
        strategy_fallback=False,
        mode="graph_augmented" if graph else "hybrid",
        top_k=5 if attempt == 0 else 8,
        score_threshold=0.0,
        dense_weight=0.5,
        sparse_weight=0.5,
        dense=ChannelExecution(requested=True, executed=True, candidates=5),
        sparse=ChannelExecution(requested=True, executed=True, candidates=5),
        graph=GraphExecution(
            requested=graph,
            executed=graph,
            hop_depth=1 if graph else None,
            nodes_visited=1 if graph else None,
            chunks_injected=1 if graph else None,
        ),
        reranker=RerankerExecution(
            requested=False,
            executed=False,
            reranker_type="none",
            latency_ms=_na("ms"),
            energy_joules=_na("joules"),
        ),
        chunks=chunks,
        latency_ms=_m(10, "ms", Provenance.MEASURED, "perf_counter"),
    )


def _verification(attempt: int, score: float, threshold: float) -> VerificationTrace:
    return VerificationTrace(
        attempt_index=attempt,
        executed=True,
        gate="default_gate",
        threshold=threshold,
        aggregated_score=_m(score, "score", Provenance.DERIVED, "weighted_mean"),
        passed=score >= threshold,
        signals=[
            SignalTrace(
                signal_type="citation_support",
                evaluator_name="CitationGroundingEvaluator",
                status="passed" if score >= threshold else "failed",
                score=score,
                weight=0.35,
                provenance=Provenance.MEASURED,
                rationale="placeholder rationale",
            )
        ],
    )


def _execution() -> ExecutionContext:
    return ExecutionContext(
        producer=MachineInfo(
            machine_id="laptop-b",
            gpu_name="NVIDIA GeForce RTX 5050 Laptop GPU",
            torch_version="2.11.0+cu128",
            cuda_version="12.8",
            git_sha="unknown",
            carbon_region="IN",
            carbon_intensity_gco2_per_kwh=None,
        ),
        served_by_machine_id="laptop-b",
        generation_source="mock",
        research_evidence=False,
    )


def example_trace_system_e() -> PipelineTrace:
    """System E: attempt 0 fails the gate, one escalation, attempt 1 passes."""
    threshold = 0.75
    attempts = [
        AttemptTrace(
            attempt_index=i,
            retrieval=_retrieval(i, graph=(i == 1)),
            generation=GenerationTrace(
                attempt_index=i,
                provider="mock",
                model_id="mock-model",
                is_local_model=False,
                finish_reason="stop",
                answer="Placeholder answer citing example/repo:src/example/module_1.py:10-20.",
                input_tokens=_m(1000, "tokens", Provenance.MEASURED, "provider_usage"),
                output_tokens=_m(100, "tokens", Provenance.MEASURED, "provider_usage"),
                latency_ms=_m(80, "ms", Provenance.MEASURED, "perf_counter"),
            ),
            verification=_verification(i, score=0.5 if i == 0 else 0.8, threshold=threshold),
            resources=_resources(),
        )
        for i in range(2)
    ]
    return PipelineTrace(
        trace_id="00000000-0000-4000-8000-000000000001",
        request_id="00000000-0000-4000-8000-000000000002",
        created_at=_CREATED_AT,
        query="How does example_function handle an empty input?",
        system=SystemId.E,
        execution=_execution(),
        classification=ClassificationTrace(
            classifier="rule_based",
            sdlc_stage="development",
            task_type="code_explanation",
            task_type_source="classifier",
            complexity="medium",
            criticality="medium",
            security_sensitivity="none",
            quality_threshold=threshold,
            quality_threshold_source="classifier",
            classifier_confidence=0.9,
            latency_ms=_m(1, "ms", Provenance.MEASURED, "perf_counter"),
        ),
        attempts=attempts,
        escalation=EscalationSummary(
            max_escalations=2,
            exhausted=False,
            steps=[
                EscalationStep(
                    from_attempt=0,
                    to_attempt=1,
                    rung="expanded_retrieval",
                    from_strategy="hybrid_balanced",
                    to_strategy="hybrid_balanced_esc1",
                    trigger_score=0.5,
                    threshold=threshold,
                    changes=[ParameterChange(name="top_k", before=5, after=8)],
                )
            ],
        ),
        outcome=Outcome(
            verdict=Verdict.VERIFIED,
            answer=attempts[-1].generation.answer,
            answer_attempt_index=1,
        ),
        totals=_resources(scale=2),
        warnings=[ILLUSTRATIVE_WARNING],
    )


def write_examples() -> Path:
    EXAMPLES_DIR.mkdir(parents=True, exist_ok=True)
    path = EXAMPLES_DIR / "trace-v1-system-e.json"
    path.write_text(
        example_trace_system_e().model_dump_json(indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return path


if __name__ == "__main__":
    print(f"wrote {write_examples()}")
