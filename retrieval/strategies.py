"""
Engineering Intelligence Hub — Retrieval Strategy Configuration
===============================================================
Pydantic models for configuring the retrieval pipeline.

A RetrievalStrategyConfig is selected by the retrieval router based on
task classification output. Named strategies are loaded from
configs/retrieval.yaml, then overridden per-experiment if needed.

Strategy examples (see configs/retrieval.yaml):
  - "dense_fast"   : vector-only, top_k=3, no reranking
  - "dense"        : vector-only, top_k=5
  - "hybrid"       : vector + BM25, reranked
  - "graph_augmented": hybrid + graph context injection
"""

from __future__ import annotations

from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field


class RetrievalMode(str, Enum):
    """Primary retrieval mode — drives which indices are queried."""
    DENSE = "dense"                  # Vector similarity only
    SPARSE = "sparse"                # BM25 / keyword only
    HYBRID = "hybrid"                # Dense + Sparse, score-fused
    GRAPH = "graph"                  # Graph traversal only
    GRAPH_AUGMENTED = "graph_augmented"  # Hybrid + graph context injection


class RerankerType(str, Enum):
    CROSS_ENCODER = "cross_encoder"
    COHERE_RERANK = "cohere_rerank"
    NONE = "none"


class RetrievalStrategyConfig(BaseModel):
    """
    Complete configuration for one retrieval strategy execution.

    All fields have sensible defaults so a strategy can be built
    incrementally during ablation studies.
    """

    strategy_name: str = Field(
        description="Human-readable name, must be unique within the strategy registry"
    )
    mode: RetrievalMode = Field(
        default=RetrievalMode.HYBRID,
        description="Primary retrieval mode",
    )
    top_k: int = Field(
        default=5,
        ge=1,
        le=50,
        description="Number of chunks to retrieve from each index",
    )
    score_threshold: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Minimum score for a chunk to be included in results",
    )
    dense_weight: float = Field(
        default=0.7,
        ge=0.0,
        le=1.0,
        description="Weight for dense (vector) score in hybrid fusion",
    )
    sparse_weight: float = Field(
        default=0.3,
        ge=0.0,
        le=1.0,
        description="Weight for sparse (BM25) score in hybrid fusion",
    )
    enable_reranking: bool = Field(
        default=False,
        description="Whether to apply a reranker after initial retrieval",
    )
    reranker_type: RerankerType = Field(
        default=RerankerType.NONE,
        description="Reranker to apply if enable_reranking=True",
    )
    reranker_top_n: int = Field(
        default=3,
        ge=1,
        description="Number of chunks to keep after reranking",
    )
    max_context_chunks: int = Field(
        default=5,
        ge=1,
        description="Maximum chunks forwarded to the generation context window",
    )
    include_graph_context: bool = Field(
        default=False,
        description="If True, supplement retrieved chunks with graph neighbour context",
    )
    graph_hop_depth: int = Field(
        default=1,
        ge=1,
        le=3,
        description="Number of graph hops to traverse for context injection",
    )
    repository_filter: Optional[str] = Field(
        default=None,
        description="If set, restrict retrieval to this repository",
    )
    artifact_type_filter: Optional[List[str]] = Field(
        default=None,
        description="If set, restrict retrieval to these artifact types",
    )

    model_config = ConfigDict(use_enum_values=True)
