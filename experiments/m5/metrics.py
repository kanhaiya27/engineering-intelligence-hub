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

    # --- 2. ESTIMATED METRICS (Modeled Proxies) ---
    cpu_energy_joules: float = Field(description="[ESTIMATED] CPU energy derived from TDP proxy: TDP * latency")
    gpu_energy_joules: float = Field(description="[ESTIMATED] GPU energy (NVML measured or TDP fallback)")
    total_energy_joules: float = Field(description="[ESTIMATED] Total system energy = CPU + GPU energy")
    cost_usd: float = Field(description="[ESTIMATED] Monetary API cost computed from pricing table")
    co2e_grams: float = Field(description="[ESTIMATED] Carbon footprint based on UK grid carbon intensity")

    # --- 3. QUALITY METRICS ---
    task_correctness: float = Field(default=0.0, ge=0.0, le=1.0, description="[MEASURED] Factual correctness against ground-truth answer (CorrectnessEvaluator)")
    citation_grounding: float = Field(default=0.0, ge=0.0, le=1.0, description="[MEASURED] Citation validity and support score (CitationGroundingEvaluator)")
    query_relevance: float = Field(default=0.0, ge=0.0, le=1.0, description="[MEASURED] Query keyword recall and relevance (QueryRelevanceEvaluator)")
    evidence_coverage: float = Field(default=0.0, ge=0.0, le=1.0, description="[MEASURED] Evidence token coverage and chunk utilization (EvidenceCoverageEvaluator)")
    evidence_consistency: float = Field(default=1.0, ge=0.0, le=1.0, description="[MEASURED] Contradiction and consistency score (EvidenceConsistencyEvaluator)")
    correctness_score: float = Field(default=0.0, ge=0.0, le=1.0, description="Alias for task_correctness")
    groundedness_score: float = Field(default=0.0, ge=0.0, le=1.0, description="Alias for evidence_coverage")
    relevance_score: float = Field(default=0.0, ge=0.0, le=1.0, description="Alias for query_relevance")
    consistency_score: float = Field(default=1.0, ge=0.0, le=1.0, description="Alias for evidence_consistency")
    citation_validity_rate: float = Field(default=1.0, ge=0.0, le=1.0, description="Ratio of valid citations")

    # --- Refusal Metrics ---
    is_grounded_refusal: bool = Field(default=False, description="True if response issued an explicit INSUFFICIENT EVIDENCE refusal")
    grounded_refusal_score: float = Field(default=0.0, ge=0.0, le=1.0, description="Refusal precision score (0.50 neutral for missing evidence, 0.0 for unfounded refusal)")

    composite_quality: float = Field(ge=0.0, le=1.0, description="Explicit weighted quality score = 40% correctness + 25% citation + 15% relevance + 10% coverage + 10% consistency")
    quality_threshold: float = Field(description="Task-specific quality requirement")
    passed_quality_gate: bool = Field(description="True if quality and correctness criteria satisfied")
    success_type: str = Field(default="QUALITY_FAILURE", description="Classification: FACTUAL_SUCCESS | VALID_REFUSAL | UNFOUNDED_REFUSAL | CITATION_FAILURE | QUALITY_FAILURE")

    # --- 4. DERIVED RESEARCH METRICS ---
    quality_constrained_success: bool = Field(
        description="[DERIVED] True if system satisfied quality and correctness requirements (composite_quality >= threshold and task_correctness >= threshold)"
    )
    quality_per_joule: float = Field(description="[DERIVED] Quality points per Joule of energy")
    quality_per_dollar: float = Field(description="[DERIVED] Quality points per USD of cost")
    quality_per_second: float = Field(description="[DERIVED] Quality points per second of latency")

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

    # Quality aggregates
    composite_quality_mean: float
    composite_quality_std: float
    composite_quality_median: float
    quality_threshold: float
    pass_rate: float

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

    # Research ratios
    quality_per_joule_mean: float
    quality_per_dollar_mean: float
    quality_per_second_mean: float
    quality_constrained_success_rate: float

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

    qualities = [t.composite_quality for t in trials]
    latencies = [t.latency_ms for t in trials]
    tokens = [float(t.total_tokens) for t in trials]
    energies = [t.total_energy_joules for t in trials]
    costs = [t.cost_usd for t in trials]
    co2s = [t.co2e_grams for t in trials]
    qpj = [t.quality_per_joule for t in trials]
    qpd = [t.quality_per_dollar for t in trials]
    qps = [t.quality_per_second for t in trials]

    q_mean = _mean(qualities)
    lat_mean = _mean(latencies)
    tok_mean = _mean(tokens)
    en_mean = _mean(energies)
    cost_mean = _mean(costs)
    co2_mean = _mean(co2s)

    passes = sum(1 for t in trials if t.passed_quality_gate) / n
    qc_successes = sum(1 for t in trials if t.quality_constrained_success) / n

    return AggregatedTaskMetrics(
        system_id=system_id,
        task_id=task_id,
        trials_count=n,
        composite_quality_mean=round(q_mean, 4),
        composite_quality_std=round(_std(qualities, q_mean), 4),
        composite_quality_median=round(_median(qualities), 4),
        quality_threshold=thresh,
        pass_rate=round(passes, 4),
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
        quality_per_joule_mean=round(_mean(qpj), 4),
        quality_per_dollar_mean=round(_mean(qpd), 2),
        quality_per_second_mean=round(_mean(qps), 4),
        quality_constrained_success_rate=round(qc_successes, 4),
    )
