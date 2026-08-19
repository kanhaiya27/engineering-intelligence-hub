"""
Engineering Intelligence Hub — Quality Verification Configuration
==================================================================
Configurable parameters and signal weights for the Phase-2 M4 Quality Gate.

IMPORTANT RESEARCH NOTE:
All signal weights (grounding, relevance, evidence_coverage, consistency)
are INITIAL BASELINE HEURISTICS for Phase-2 experimental exploration.
They are NOT claimed to be optimal.
They will be empirically validated and ablated in Phase-2 M5 evaluation.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from pydantic import BaseModel, ConfigDict, Field


class VerificationConfig(BaseModel):
    """
    Configuration for quality verification and escalation behavior.

    All weights and thresholds are configurable per-request or per-experiment
    to facilitate ablation studies.
    """

    # --- Heuristic Signal Weights (Baseline Defaults) ---
    citation_grounding_weight: float = Field(
        default=0.35,
        ge=0.0,
        description="Weight of citation grounding signal in aggregated quality score",
    )
    query_relevance_weight: float = Field(
        default=0.25,
        ge=0.0,
        description="Weight of query relevance signal in aggregated quality score",
    )
    evidence_coverage_weight: float = Field(
        default=0.20,
        ge=0.0,
        description="Weight of evidence coverage signal in aggregated quality score",
    )
    evidence_consistency_weight: float = Field(
        default=0.20,
        ge=0.0,
        description="Weight of evidence consistency signal in aggregated quality score",
    )

    # --- Thresholds & Escalation Limits ---
    default_quality_threshold: float = Field(
        default=0.75,
        ge=0.0,
        le=1.0,
        description="Fallback minimum quality score if not specified by task classification",
    )
    max_escalation_attempts: int = Field(
        default=2,
        ge=0,
        le=5,
        description="Maximum retrieval escalation attempts before returning INSUFFICIENT_EVIDENCE",
    )
    enforce_strict_citations: bool = Field(
        default=False,
        description="If True, missing citations for factual assertions trigger hard failure",
    )

    # --- Top-k / Graph Escalation Deltas ---
    escalation_top_k_delta: int = Field(
        default=3,
        ge=1,
        description="Number of additional chunks to request on each escalation step",
    )
    escalation_graph_depth: int = Field(
        default=2,
        ge=1,
        le=3,
        description="Graph hop depth to activate on graph escalation attempt",
    )

    # --- Metadata / Provenance ---
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Extra experiment tags or ablation metadata",
    )

    model_config = ConfigDict(use_enum_values=True)
