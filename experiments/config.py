"""
Engineering Intelligence Hub — Experiment Configuration Schema
==============================================================
Defines ExperimentConfig: the complete, self-describing configuration
for one experimental run. Every result row in the experiment log must
be traceable to an ExperimentConfig.

Reproducibility principle:
  Given an ExperimentConfig, the experiment should be exactly reproducible
  by another researcher on the same hardware and with the same API keys.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field


class ExperimentType(str, Enum):
    """High-level category of the experiment."""
    BASELINE = "baseline"
    ABLATION = "ablation"
    COMPARISON = "comparison"
    PILOT = "pilot"
    EVALUATION = "evaluation"


class BaselineID(str, Enum):
    """
    Named baselines from the experiment plan.
    A: LLM only (no RAG)
    B: Fixed RAG + fixed model
    C: Hybrid RAG + fixed model
    D: Adaptive retrieval
    E: Adaptive retrieval + model routing
    F: Adaptive retrieval + model routing + quality gate
    """
    BASELINE_A = "baseline_a"
    BASELINE_B = "baseline_b"
    BASELINE_C = "baseline_c"
    EXPERIMENT_D = "experiment_d"
    EXPERIMENT_E = "experiment_e"
    EXPERIMENT_F = "experiment_f"
    ADVANCED = "advanced"
    CUSTOM = "custom"


class ExperimentConfig(BaseModel):
    """
    Complete configuration for one experiment run.

    This is the ground truth for reproducibility. Log this alongside
    every ExperimentResult so results can always be traced to their config.
    """

    # --- Identity ---
    experiment_id: str = Field(description="Unique experiment identifier, e.g. 'eih-baseline-a-20250815'")
    experiment_name: str = Field(description="Human-readable experiment name")
    experiment_type: ExperimentType = Field(default=ExperimentType.BASELINE)
    baseline_id: Optional[BaselineID] = Field(
        default=None,
        description="Maps to a named baseline from EXPERIMENT_PLAN.md",
    )
    description: str = Field(default="", description="Free-text description of this run")

    # --- Model configuration ---
    model_id: str = Field(description="Model ID used for generation")
    model_provider: str = Field(description="Provider name (openai, anthropic, google, local, etc.)")
    model_temperature: float = Field(default=0.1)
    model_max_tokens: int = Field(default=2048)

    # --- Retrieval configuration ---
    retrieval_strategy_name: Optional[str] = Field(
        default=None,
        description="Name of the retrieval strategy (from configs/retrieval.yaml). None = no RAG.",
    )
    retrieval_top_k: Optional[int] = None
    enable_reranking: bool = False
    reranker_type: Optional[str] = None

    # --- Routing configuration ---
    routing_enabled: bool = Field(
        default=False, description="True if adaptive model routing is active"
    )
    routing_policy_name: Optional[str] = None

    # --- Quality gate ---
    quality_gate_enabled: bool = Field(default=False)
    quality_threshold: float = Field(default=0.75, ge=0.0, le=1.0)
    max_escalations: int = Field(default=0)

    # --- Graph ---
    graph_retrieval_enabled: bool = Field(default=False)
    graph_hop_depth: int = Field(default=1)

    # --- Benchmark ---
    benchmark_task_ids: List[str] = Field(
        default_factory=list,
        description="Specific task IDs to evaluate. Empty = run all APPROVED tasks.",
    )
    benchmark_split: Optional[str] = Field(
        default=None, description="train | validation | test"
    )

    # --- Sustainability ---
    sustainability_enabled: bool = Field(
        default=True, description="Collect sustainability estimates"
    )
    carbon_region: str = Field(
        default="uk_national_grid_2024",
        description="Carbon intensity region key for CO2e estimation",
    )

    # --- Ablation flags ---
    ablation_flags: Dict[str, bool] = Field(
        default_factory=dict,
        description=(
            "Ablation study flags, e.g. "
            "{'disable_reranking': True, 'disable_graph': True}"
        ),
    )

    # --- Execution ---
    seed: int = Field(default=42, description="Random seed for reproducibility")
    num_runs: int = Field(default=1, description="Number of repeated runs for variance estimation")
    tags: List[str] = Field(default_factory=list, description="Free-form tags for filtering results")
    created_at: Optional[str] = None
    git_commit_sha: Optional[str] = Field(
        default=None,
        description="Git SHA of the codebase at time of experiment — populated at runtime",
    )
    extra: Dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(use_enum_values=True)
