"""
Engineering Intelligence Hub — Evaluation Metrics
==================================================
Pydantic models for quality and efficiency metrics collected per
experiment run. These form the rows of the experiment results table.

Research metrics defined here are PROPOSED metrics — they are named
and described as such. They are not established industry standards.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from pydantic import BaseModel, Field


class QualityMetrics(BaseModel):
    """Task-level quality metrics."""

    task_id: str
    task_correctness: Optional[float] = Field(
        default=None,
        description="Correctness score (0–1) — requires ground truth",
        ge=0.0, le=1.0,
    )
    groundedness: Optional[float] = Field(
        default=None,
        description="Groundedness score: extent answer is supported by retrieved context",
        ge=0.0, le=1.0,
    )
    relevance: Optional[float] = Field(
        default=None,
        description="Relevance score: extent answer addresses the query",
        ge=0.0, le=1.0,
    )
    code_compilation_success: Optional[bool] = Field(
        default=None,
        description="True if generated code compiled/parsed successfully",
    )
    test_execution_success: Optional[bool] = Field(
        default=None,
        description="True if generated tests passed against target code",
    )
    diagnosis_correctness: Optional[float] = Field(
        default=None,
        description="For incident/error analysis tasks: diagnosis correctness (0–1)",
        ge=0.0, le=1.0,
    )
    security_check_passed: Optional[bool] = Field(
        default=None,
        description="True if no security issues were detected in generated output",
    )
    aggregated_quality_score: Optional[float] = Field(
        default=None,
        description="Weighted aggregate of applicable quality signals (0–1)",
        ge=0.0, le=1.0,
    )
    quality_threshold: Optional[float] = Field(
        default=None,
        description="The threshold that was applied",
    )
    passed_quality_gate: Optional[bool] = None


class EfficiencyMetrics(BaseModel):
    """Task-level efficiency and resource metrics."""

    task_id: str
    # --- Latency ---
    latency_ms: Optional[float] = Field(
        default=None, description="End-to-end wall-clock latency in milliseconds"
    )
    # --- Tokens ---
    input_tokens: Optional[int] = None
    output_tokens: Optional[int] = None
    total_tokens: Optional[int] = None
    # --- Cost ---
    cost_usd: Optional[float] = Field(
        default=None, description="Estimated monetary cost in USD"
    )
    # --- Energy ---
    energy_joules: Optional[float] = Field(
        default=None,
        description="Estimated energy in joules — see sustainability boundary docs",
    )
    energy_estimation_method: Optional[str] = None
    # --- Carbon ---
    co2e_grams: Optional[float] = Field(
        default=None,
        description="Estimated CO2e in grams — see sustainability boundary docs",
    )
    carbon_intensity_gco2_kwh: Optional[float] = None
    carbon_region: Optional[str] = None
    # --- System ---
    cpu_utilisation_pct: Optional[float] = None
    gpu_utilisation_pct: Optional[float] = None
    # --- RAG ---
    num_chunks_retrieved: Optional[int] = None
    retrieval_latency_ms: Optional[float] = None
    retrieval_strategy: Optional[str] = None
    # --- Escalation ---
    num_retries: int = 0
    num_escalations: int = 0
    model_id: Optional[str] = None


class EngineeringOutcomeMetrics(BaseModel):
    """
    Engineering-outcome metrics for a completed task.

    These metrics capture the impact on developer workflow.
    'Rework' and 'developer effort' are hard to measure directly —
    document proxy assumptions clearly.
    """

    task_id: str
    task_completed: bool = Field(
        description="True if the task was completed successfully"
    )
    escalation_count: int = 0
    retry_count: int = 0
    # Rework estimate — proxy: 1.0 if escalated, 0.0 if first-pass success
    rework_proxy_score: Optional[float] = Field(
        default=None,
        description=(
            "PROXY metric: estimated rework risk (0=no rework, 1=full rework). "
            "Computed as: 1 - (1 / (1 + escalation_count + retry_count)). "
            "This is a research proxy, not a direct measurement."
        ),
        ge=0.0, le=1.0,
    )
    developer_effort_proxy_minutes: Optional[float] = Field(
        default=None,
        description=(
            "PROXY metric: estimated developer effort in minutes. "
            "Not directly measured — document how this is derived."
        ),
    )


class ExperimentResult(BaseModel):
    """
    Complete result record for one task execution in an experiment.

    This is the unit of analysis for all efficiency/quality trade-off
    studies, Pareto analysis, and ablation studies.
    """

    # --- Identity ---
    result_id: str
    experiment_id: str
    task_id: str
    run_index: int = Field(
        default=0,
        description="Run index for repeated execution (for variance estimation)",
    )
    created_at: Optional[str] = None

    # --- Configuration ---
    experiment_config_name: Optional[str] = None
    model_id: Optional[str] = None
    retrieval_strategy: Optional[str] = None
    quality_threshold: Optional[float] = None
    routing_policy_name: Optional[str] = None

    # --- Metrics ---
    quality: Optional[QualityMetrics] = None
    efficiency: Optional[EfficiencyMetrics] = None
    outcome: Optional[EngineeringOutcomeMetrics] = None

    # --- Proposed research metrics (clearly labelled) ---
    # PROPOSED: Energy per Successful Engineering Task
    energy_per_successful_task_joules: Optional[float] = Field(
        default=None,
        description=(
            "PROPOSED RESEARCH METRIC: energy_joules / (1 if task_completed else 0). "
            "Infinity if task failed. Compare across configurations at fixed quality threshold."
        ),
    )
    # PROPOSED: CO2e per Successful Engineering Task
    co2e_per_successful_task_grams: Optional[float] = Field(
        default=None,
        description=(
            "PROPOSED RESEARCH METRIC: co2e_grams / (1 if task_completed else 0). "
            "Infinity if task failed."
        ),
    )
    # PROPOSED: Quality-Constrained Energy Efficiency
    quality_constrained_efficiency: Optional[float] = Field(
        default=None,
        description=(
            "PROPOSED RESEARCH METRIC: quality_score / energy_joules, "
            "computed only when quality >= threshold. "
            "Higher is better. Units: quality-points per joule."
        ),
    )

    # --- Raw outputs ---
    answer_text: Optional[str] = None
    error_message: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)

    def compute_proposed_metrics(self) -> None:
        """
        Compute the proposed research metrics from quality and efficiency data.
        Call this after populating quality and efficiency fields.
        """
        if self.efficiency is None or self.quality is None:
            return

        task_ok = self.outcome.task_completed if self.outcome else False
        energy_j = self.efficiency.energy_joules
        co2e_g = self.efficiency.co2e_grams
        q_score = self.quality.aggregated_quality_score

        if energy_j is not None:
            self.energy_per_successful_task_joules = energy_j if task_ok else float("inf")

        if co2e_g is not None:
            self.co2e_per_successful_task_grams = co2e_g if task_ok else float("inf")

        if q_score is not None and energy_j is not None and energy_j > 0:
            passed_gate = self.quality.passed_quality_gate or False
            if passed_gate:
                self.quality_constrained_efficiency = round(q_score / energy_j, 8)
