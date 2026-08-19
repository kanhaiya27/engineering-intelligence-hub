"""
Engineering Intelligence Hub — Adaptive Retrieval Policy Engine
===============================================================
Centralised, configurable task-type → retrieval policy mapping.

IMPORTANT RESEARCH NOTE:
These are INITIAL HEURISTIC POLICIES for experimental baseline configuration.
They are NOT claimed to be optimal or Pareto-efficient.
All parameters are explicitly labelled as heuristic defaults and must be
validated experimentally in Phase-2 M5 controlled evaluation.

Policy Families:
  1. REQUIREMENTS     → dense_fast (semantic, low context)
  2. CODE_LOOKUP      → sparse_heavy (BM25-dominant, symbol-aware)
  3. CODE_DEV         → hybrid (balanced dense+BM25)
  4. TESTING          → hybrid (moderate top-k)
  5. ARCHITECTURE     → graph_augmented (hybrid + graph context)
  6. INCIDENT         → incident_graph (sparse-heavy + graph provenance)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Optional

import yaml

from core.logging import get_logger
from knowledge.schemas.tasks import (
    ComplexityLevel,
    CriticalityLevel,
    SDLCStage,
    TaskClassification,
    TaskType,
)
from retrieval.strategies import RetrievalMode, RetrievalStrategyConfig

logger = get_logger(__name__)


@dataclass(frozen=True)
class PolicyKey:
    """
    Composite lookup key for retrieval policy resolution.
    More specific keys take precedence over general ones.
    """
    task_type: Optional[str] = None
    sdlc_stage: Optional[str] = None
    complexity: Optional[str] = None
    criticality: Optional[str] = None


# ---------------------------------------------------------------------------
# Default task_type → strategy_name mapping
# (initial heuristic configuration — not validated as optimal)
# ---------------------------------------------------------------------------

_TASK_TYPE_STRATEGY_MAP: Dict[str, str] = {
    # Requirements: Semantic lookup, small context
    TaskType.REQUIREMENT_UNDERSTANDING: "dense_fast",
    TaskType.REQUIREMENT_RETRIEVAL: "dense_fast",

    # Architecture: Graph-augmented for dependency traversal
    TaskType.ARCHITECTURE_QA: "graph_augmented",
    TaskType.DEPENDENCY_UNDERSTANDING: "graph_augmented",
    TaskType.ARCHITECTURE_DECISION_SUPPORT: "graph_augmented",

    # Development: Standard hybrid
    TaskType.CODE_EXPLANATION: "hybrid",
    TaskType.CODE_GENERATION: "hybrid",
    TaskType.REPOSITORY_ASSISTANCE: "hybrid",

    # Testing: Hybrid with test file filtering
    TaskType.TEST_GENERATION: "hybrid",
    TaskType.TEST_EXPLANATION: "hybrid",
    TaskType.TEST_FAILURE_ANALYSIS: "hybrid",

    # Code Review: BM25-weighted hybrid
    TaskType.DEFECT_DETECTION: "hybrid_bm25",
    TaskType.RISK_IDENTIFICATION: "hybrid_bm25",
    TaskType.REVIEW_ASSISTANCE: "hybrid",

    # Deployment / Change Impact
    TaskType.CHANGE_IMPACT_ANALYSIS: "graph_augmented",
    TaskType.DEPENDENCY_ANALYSIS: "graph_augmented",

    # Operations / Incident: Sparse-dominant + graph
    TaskType.ERROR_ANALYSIS: "incident_graph",
    TaskType.INCIDENT_RETRIEVAL: "incident_sparse",
    TaskType.ROOT_CAUSE_ASSISTANCE: "incident_graph",

    # Maintenance: Historical + hybrid
    TaskType.TECHNICAL_DEBT_ANALYSIS: "hybrid",
    TaskType.CHANGE_UNDERSTANDING: "hybrid",
    TaskType.HISTORICAL_REASONING: "incident_sparse",
}

# Criticality → strategy escalation (overrides task_type mapping for HIGH/CRITICAL)
_CRITICALITY_OVERRIDE_MAP: Dict[str, str] = {
    CriticalityLevel.CRITICAL: "graph_augmented_reranked",
    CriticalityLevel.HIGH: "hybrid_reranked",
}

# Default fallback
_DEFAULT_STRATEGY = "hybrid"


class AdaptiveRetrievalPolicy:
    """
    Adaptive task-to-retrieval policy resolver.

    Resolves the most appropriate RetrievalStrategyConfig given a TaskClassification.
    Resolution order:
      1. Criticality override (CRITICAL / HIGH → stronger strategy)
      2. task_type → strategy mapping
      3. Fallback: "hybrid"

    All resolution results are logged for experiment tracing.
    """

    def __init__(self, strategy_registry: Dict[str, RetrievalStrategyConfig]) -> None:
        self._registry = strategy_registry

    def resolve(
        self,
        classification: TaskClassification,
        override_strategy_name: Optional[str] = None,
    ) -> RetrievalStrategyConfig:
        """
        Resolve retrieval strategy for a given task classification.

        Parameters
        ----------
        classification : TaskClassification
        override_strategy_name : str, optional
            Force a specific named strategy (ablation experiments).

        Returns
        -------
        RetrievalStrategyConfig
        """
        # 0. Explicit override for ablation studies
        if override_strategy_name:
            return self._get_strategy(override_strategy_name, reason="explicit_override")

        # 1. Criticality escalation (CRITICAL or HIGH → stronger strategy)
        crit = classification.criticality
        if crit in _CRITICALITY_OVERRIDE_MAP:
            strat_name = _CRITICALITY_OVERRIDE_MAP[crit]
            if strat_name in self._registry:
                logger.debug(
                    f"Task {classification.task_id}: criticality={crit} → escalated to '{strat_name}'"
                )
                return self._get_strategy(strat_name, reason=f"criticality_escalation:{crit}")

        # 2. Task-type → strategy lookup
        strat_name = _TASK_TYPE_STRATEGY_MAP.get(classification.task_type, _DEFAULT_STRATEGY)

        # 3. Graph context: only enable if strategy has graph support in registry
        resolved = self._get_strategy(strat_name, reason=f"task_type:{classification.task_type}")

        logger.debug(
            f"Task {classification.task_id}: type={classification.task_type} "
            f"→ strategy='{strat_name}', graph={resolved.include_graph_context}"
        )
        return resolved

    def _get_strategy(
        self, name: str, reason: str = "lookup"
    ) -> RetrievalStrategyConfig:
        if name in self._registry:
            return self._registry[name]
        logger.warning(
            f"Strategy '{name}' not in registry (reason: {reason}). Falling back to '{_DEFAULT_STRATEGY}'."
        )
        if _DEFAULT_STRATEGY in self._registry:
            return self._registry[_DEFAULT_STRATEGY]
        # Last resort: bare default config
        return RetrievalStrategyConfig(strategy_name=_DEFAULT_STRATEGY)

    def list_policies(self) -> Dict[str, str]:
        """Return the task_type → strategy_name mapping for inspection."""
        return dict(_TASK_TYPE_STRATEGY_MAP)

    def list_criticality_overrides(self) -> Dict[str, str]:
        """Return the criticality → strategy_name override map."""
        return dict(_CRITICALITY_OVERRIDE_MAP)
