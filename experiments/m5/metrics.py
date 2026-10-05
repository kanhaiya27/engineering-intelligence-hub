"""
Engineering Intelligence Hub — Controlled Metrics & Telemetry Schema (M5)
=========================================================================
Strict 3-Tier Metric Categorization:
  1. MEASURED  : Direct empirical hardware / software measurements (time, tokens, NVML power)
  2. ESTIMATED : Modeled physical / financial proxies (TDP CPU energy, API pricing, grid carbon)
  3. DERIVED   : Research ratios, Pareto dominance, and quality-constrained efficiency deltas

Core Research Principle:
Quality-Constrained Energy Efficiency enforces that resource savings are only valid
if Answer Quality >= Task-Specific Quality Threshold.
"""

from __future__ import annotations

import math
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field


class TrialResult(BaseModel):
    """
    Complete telemetry and evaluation result for one single task trial execution.
    """
    # --- Experiment Identity ---
    experiment_id: str
    system_id: str
    task_id: str
    benchmark_version: str
    dataset_split: str  # "dev" | "val" | "test"
    trial_index: int    # 0, 1, 2...
    timestamp: str
    manifest_hash: str

    # --- 1. MEASURED METRICS (Direct Readings) ---
    latency_ms: float = Field(description="[MEASURED] Total wall-clock execution duration in ms")
    retrieval_latency_ms: float = Field(default=0.0, description="[MEASURED] Retrieval wall-clock duration in ms")
    generation_latency_ms: float = Field(default=0.0, description="[MEASURED] Generation wall-clock duration in ms")
    input_tokens: int = Field(default=0, description="[MEASURED] Exact input token count")
    output_tokens: int = Field(default=0, description="[MEASURED] Exact output token count")
    total_tokens: int = Field(default=0, description="[MEASURED] Total tokens consumed")
    retrieval_calls_count: int = Field(default=0, description="[MEASURED] Number of retrieval operations executed")
    chunks_retrieved_count: int = Field(default=0, description="[MEASURED] Total context chunks retrieved")
    graph_chunks_count: int = Field(default=0, description="[MEASURED] Total graph context chunks injected")
    escalation_count: int = Field(default=0, description="[MEASURED] Number of escalation steps performed")
    total_attempts: int = Field(default=1, description="[MEASURED] Total generation attempts")
    gpu_energy_measured_joules: Optional[float] = Field(
        default=None,
        description="[MEASURED] Direct GPU energy reading via NVML API (if available)",
    )

    # --- 2. ENERGY / COST / CARBON (tiers as defined in the original plan §9.1) ---
    cpu_energy_joules: Optional[float] = Field(
        default=None, description="[ESTIMATED] CPU TDP x system-wide CPU utilisation over the trial x duration")
    gpu_energy_joules: float = Field(
        description="GPU board energy: NVML-counter generation energy + rerank estimate if any; tier in energy_tier")
    total_energy_joules: float = Field(
        description="[ESTIMATED] GPU + CPU energy; tier in total_energy_tier")
    energy_tier: Optional[str] = Field(
        default=None, description="Tier of gpu_energy_joules: MEASURED, or ESTIMATED if a rerank sample is included")
    total_energy_tier: Optional[str] = Field(
        default=None, description="Weakest tier of the total (ESTIMATED whenever CPU energy is included)")
    gpu_max_temp_c: Optional[float] = Field(
        default=None, description="[MEASURED] Highest GPU temperature seen during the trial's generation calls")
    cost_usd: float = Field(description="[ESTIMATED] monetary cost; 0 for local inference")
    co2e_grams: float = Field(description="[ESTIMATED] total energy x the manifest's grid carbon intensity")
    latency_breakdown_ms: Optional[Dict[str, float]] = Field(
        default=None, description="[MEASURED] T_query, T_retrieval, T_rerank, T_context, T_generation (+ other) of §9.2")
    output_truncated: Optional[bool] = Field(
        default=None, description="[MEASURED] True if any generation stopped at the output-token limit")

    # --- 3. QUALITY METRICS ---
    # None = the evaluator produced no score. Missing scores are never filled with an
    # invented value (the runner used to substitute 0.50); such trials are excluded from
    # quality aggregates and counted (`missing_scores`, AggregatedTaskMetrics.trials_missing_scores).
    task_correctness: Optional[float] = Field(default=None, ge=0.0, le=1.0, description="[MEASURED] Set-based token F1 against the ground-truth answer or best alternative (CorrectnessEvaluator; lexical)")
    citation_grounding: Optional[float] = Field(default=None, ge=0.0, le=1.0, description="[MEASURED] System E gate signal: citations vs RETRIEVED chunks (CitationGroundingEvaluator)")
    query_relevance: Optional[float] = Field(default=None, ge=0.0, le=1.0, description="[MEASURED] System E gate signal: query keyword recall (QueryRelevanceEvaluator)")
    evidence_coverage: Optional[float] = Field(default=None, ge=0.0, le=1.0, description="[MEASURED] System E gate signal: evidence token coverage (EvidenceCoverageEvaluator)")
    evidence_consistency: Optional[float] = Field(default=None, ge=0.0, le=1.0, description="[MEASURED] System E gate signal: contradiction check (EvidenceConsistencyEvaluator)")
    correctness_score: Optional[float] = Field(default=None, ge=0.0, le=1.0, description="Alias for task_correctness")
    groundedness_score: Optional[float] = Field(default=None, ge=0.0, le=1.0, description="Alias for evidence_coverage")
    relevance_score: Optional[float] = Field(default=None, ge=0.0, le=1.0, description="Alias for query_relevance")
    consistency_score: Optional[float] = Field(default=None, ge=0.0, le=1.0, description="Alias for evidence_consistency")
    citation_validity_rate: Optional[float] = Field(default=None, ge=0.0, le=1.0, description="Ratio of valid citations (None if the answer cites nothing)")
    missing_scores: List[str] = Field(default_factory=list, description="Quality components the evaluators did not score")

    # --- Independent outcome (evaluation/outcome.py): answer text vs the human-checked evidence
    #     spans only; never the retrieved chunks or System E's gate signals (RQ3 without circularity)
    has_retrieval_label: bool = Field(default=False, description="A retrieval label exists for this task")
    line_citations: int = Field(default=0, description="[MEASURED] [path:Lx-Ly] citations in the answer")
    cited_span_precision: Optional[float] = Field(default=None, description="[MEASURED] Share of line citations inside a labelled evidence span")
    cited_span_recall: Optional[float] = Field(default=None, description="[MEASURED] Share of labelled spans cited")
    cited_file_recall: Optional[float] = Field(default=None, description="[MEASURED] Share of labelled relevant files cited")
    answer_supported: Optional[bool] = Field(default=None, description="[MEASURED] Non-refusal answer citing >= 1 labelled span; None for refusals or without a label")

    # --- Refusal Metrics ---
    is_grounded_refusal: bool = Field(default=False, description="True if response issued an explicit INSUFFICIENT EVIDENCE refusal")
    grounded_refusal_score: float = Field(default=0.0, ge=0.0, le=1.0, description="Refusal precision score (0.50 neutral for missing evidence, 0.0 for unfounded refusal)")

    composite_quality: Optional[float] = Field(default=None, ge=0.0, le=1.0, description="Weighted score = 40% correctness + 25% citation + 15% relevance + 10% coverage + 10% consistency; None if any component is missing")
    quality_threshold: float = Field(description="Task-specific quality requirement")
    passed_quality_gate: Optional[bool] = Field(default=None, description="True if quality and correctness criteria satisfied; None if scores are missing")
    success_type: str = Field(default="QUALITY_FAILURE", description="Classification: FACTUAL_SUCCESS | VALID_REFUSAL | UNFOUNDED_REFUSAL | CITATION_FAILURE | QUALITY_FAILURE | MISSING_SCORES")

    # --- 4. DERIVED RESEARCH METRICS ---
    quality_constrained_success: Optional[bool] = Field(
        default=None,
        description="[DERIVED] True if system satisfied quality and correctness requirements (composite_quality >= threshold and task_correctness >= threshold); None if scores are missing"
    )
    quality_per_joule: Optional[float] = Field(default=None, description="[DERIVED] Quality points per Joule of energy")
    quality_per_dollar: Optional[float] = Field(default=None, description="[DERIVED] Quality points per USD of cost")
    quality_per_second: Optional[float] = Field(default=None, description="[DERIVED] Quality points per second of latency")

    # Raw Artifacts
    generated_answer: str = Field(description="Generated output text")
    metadata: Dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(use_enum_values=True)


class AggregatedTaskMetrics(BaseModel):
    """
    Aggregated summary over N repeated trials for a single system and task.
    """
    system_id: str
    task_id: str
    trials_count: int

    # Quality aggregates (over trials with all quality scores; None if there are none)
    trials_missing_scores: int = 0
    composite_quality_mean: Optional[float]
    composite_quality_std: Optional[float]
    composite_quality_median: Optional[float]
    quality_threshold: float
    pass_rate: Optional[float]

    # Efficiency aggregates
    latency_ms_mean: float
    latency_ms_std: float
    latency_ms_median: float
    total_tokens_mean: float
    total_tokens_std: float
    total_energy_joules_mean: float
    total_energy_joules_std: float
    cost_usd_mean: float
    cost_usd_std: float
    co2e_grams_mean: float
    co2e_grams_std: float

    # Research ratios (over scored trials)
    quality_per_joule_mean: Optional[float]
    quality_per_dollar_mean: Optional[float]
    quality_per_second_mean: Optional[float]
    quality_constrained_success_rate: Optional[float]

    model_config = ConfigDict(use_enum_values=True)


def compute_trial_aggregates(trials: List[TrialResult]) -> AggregatedTaskMetrics:
    """
    Compute mean, median, and sample standard deviation across N repeated trials.
    """
    if not trials:
        raise ValueError("Cannot aggregate empty list of trials")

    n = len(trials)
    system_id = trials[0].system_id
    task_id = trials[0].task_id
    thresh = trials[0].quality_threshold

    def _mean(values: List[float]) -> float:
        return sum(values) / len(values) if values else 0.0

    def _std(values: List[float], m: float) -> float:
        if len(values) <= 1:
            return 0.0
        variance = sum((x - m) ** 2 for x in values) / (len(values) - 1)
        return math.sqrt(variance)

    def _median(values: List[float]) -> float:
        s = sorted(values)
        mid = len(s) // 2
        return (s[mid] if len(s) % 2 != 0 else (s[mid - 1] + s[mid]) / 2.0) if s else 0.0

    scored = [t for t in trials if t.composite_quality is not None]
    qualities = [t.composite_quality for t in scored]
    latencies = [t.latency_ms for t in trials]
    tokens = [float(t.total_tokens) for t in trials]
    energies = [t.total_energy_joules for t in trials]
    costs = [t.cost_usd for t in trials]
    co2s = [t.co2e_grams for t in trials]
    qpj = [t.quality_per_joule for t in scored]
    qpd = [t.quality_per_dollar for t in scored]
    qps = [t.quality_per_second for t in scored]

    def _r(x: Optional[float], nd: int) -> Optional[float]:
        return None if x is None else round(x, nd)

    q_mean = _mean(qualities) if scored else None
    lat_mean = _mean(latencies)
    tok_mean = _mean(tokens)
    en_mean = _mean(energies)
    cost_mean = _mean(costs)
    co2_mean = _mean(co2s)

    passes = sum(1 for t in scored if t.passed_quality_gate) / len(scored) if scored else None
    qc_successes = sum(1 for t in scored if t.quality_constrained_success) / len(scored) if scored else None

    return AggregatedTaskMetrics(
        system_id=system_id,
        task_id=task_id,
        trials_count=n,
        trials_missing_scores=n - len(scored),
        composite_quality_mean=_r(q_mean, 4),
        composite_quality_std=_r(_std(qualities, q_mean), 4) if scored else None,
        composite_quality_median=_r(_median(qualities), 4) if scored else None,
        quality_threshold=thresh,
        pass_rate=_r(passes, 4),
        latency_ms_mean=round(lat_mean, 2),
        latency_ms_std=round(_std(latencies, lat_mean), 2),
        latency_ms_median=round(_median(latencies), 2),
        total_tokens_mean=round(tok_mean, 1),
        total_tokens_std=round(_std(tokens, tok_mean), 1),
        total_energy_joules_mean=round(en_mean, 4),
        total_energy_joules_std=round(_std(energies, en_mean), 4),
        cost_usd_mean=round(cost_mean, 6),
        cost_usd_std=round(_std(costs, cost_mean), 6),
        co2e_grams_mean=round(co2_mean, 6),
        co2e_grams_std=round(_std(co2s, co2_mean), 6),
        quality_per_joule_mean=_r(_mean(qpj), 4) if scored else None,
        quality_per_dollar_mean=_r(_mean(qpd), 2) if scored else None,
        quality_per_second_mean=_r(_mean(qps), 4) if scored else None,
        quality_constrained_success_rate=_r(qc_successes, 4),
    )
