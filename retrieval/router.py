"""
Engineering Intelligence Hub — Retrieval Strategy Router
=========================================================
Selects the appropriate RetrievalStrategyConfig for a given task.

In Phase-0 this is a pure configuration-driven lookup: a named strategy
is resolved from a registry loaded from configs/retrieval.yaml.

Phase-2 will introduce a learned/heuristic router that maps task
classification features to the Pareto-optimal strategy.
"""

from __future__ import annotations

from typing import Dict, Optional

import yaml

from core.exceptions import InvalidRetrievalStrategyError
from core.logging import get_logger
from knowledge.schemas.tasks import TaskClassification, TaskType
from retrieval.strategies import RetrievalStrategyConfig

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Default strategy per task type (configuration-driven initial routing)
# ---------------------------------------------------------------------------

_DEFAULT_STRATEGY_MAP: Dict[str, str] = {
    # Documentation / Requirements
    TaskType.REQUIREMENT_UNDERSTANDING: "hybrid",
    TaskType.REQUIREMENT_RETRIEVAL: "hybrid",
    # Architecture
    TaskType.ARCHITECTURE_QA: "graph_augmented",
    TaskType.DEPENDENCY_UNDERSTANDING: "graph_augmented",
    TaskType.ARCHITECTURE_DECISION_SUPPORT: "graph_augmented",
    # Development
    TaskType.CODE_EXPLANATION: "hybrid",
    TaskType.CODE_GENERATION: "dense",
    TaskType.REPOSITORY_ASSISTANCE: "hybrid",
    # Testing
    TaskType.TEST_GENERATION: "dense",
    TaskType.TEST_EXPLANATION: "hybrid",
    TaskType.TEST_FAILURE_ANALYSIS: "hybrid",
    # Code review
    TaskType.DEFECT_DETECTION: "hybrid",
    TaskType.RISK_IDENTIFICATION: "hybrid",
    TaskType.REVIEW_ASSISTANCE: "hybrid",
    # Deployment
    TaskType.CHANGE_IMPACT_ANALYSIS: "graph_augmented",
    TaskType.DEPENDENCY_ANALYSIS: "graph_augmented",
    # Operations
    TaskType.ERROR_ANALYSIS: "hybrid",
    TaskType.INCIDENT_RETRIEVAL: "sparse",
    TaskType.ROOT_CAUSE_ASSISTANCE: "hybrid",
    # Maintenance
    TaskType.TECHNICAL_DEBT_ANALYSIS: "hybrid",
    TaskType.CHANGE_UNDERSTANDING: "hybrid",
    TaskType.HISTORICAL_REASONING: "sparse",
}


class RetrievalRouter:
    """
    Configuration-driven retrieval strategy router.

    Loads named strategies from a YAML registry and resolves the
    appropriate strategy name for a given task classification.
    """

    def __init__(self, strategy_registry: Optional[Dict[str, RetrievalStrategyConfig]] = None) -> None:
        self._registry: Dict[str, RetrievalStrategyConfig] = strategy_registry or {}

    @classmethod
    def from_yaml(cls, yaml_path: str) -> "RetrievalRouter":
        """
        Build a RetrievalRouter by loading named strategies from a YAML file.

        Parameters
        ----------
        yaml_path : str
            Path to configs/retrieval.yaml.
        """
        with open(yaml_path, "r", encoding="utf-8") as f:
            raw = yaml.safe_load(f) or {}

        registry: Dict[str, RetrievalStrategyConfig] = {}
        for name, params in raw.get("strategies", {}).items():
            params["strategy_name"] = name
            registry[name] = RetrievalStrategyConfig(**params)

        logger.info(f"RetrievalRouter loaded {len(registry)} strategies from {yaml_path}")
        return cls(strategy_registry=registry)

    def register(self, strategy: RetrievalStrategyConfig) -> None:
        """Add or replace a strategy in the in-memory registry."""
        self._registry[strategy.strategy_name] = strategy

    def resolve(
        self,
        classification: TaskClassification,
        override_strategy_name: Optional[str] = None,
    ) -> RetrievalStrategyConfig:
        """
        Resolve the retrieval strategy for a classified task.

        Resolution order:
        1. override_strategy_name (explicit caller override)
        2. Task-type → strategy name from _DEFAULT_STRATEGY_MAP
        3. Fall back to "hybrid" if no match

        Parameters
        ----------
        classification : TaskClassification
        override_strategy_name : str, optional
            Force a specific named strategy (used in ablation studies).

        Returns
        -------
        RetrievalStrategyConfig
        """
        strategy_name = override_strategy_name
        if strategy_name is None:
            strategy_name = _DEFAULT_STRATEGY_MAP.get(
                classification.task_type, "hybrid"
            )

        if strategy_name not in self._registry:
            if self._registry:
                raise InvalidRetrievalStrategyError(
                    f"Strategy '{strategy_name}' not found in registry.",
                    details=f"Available: {list(self._registry.keys())}",
                )
            # No registry loaded yet (Phase-0) — return a sensible default.
            logger.warning(
                f"No strategy registry loaded. Returning default hybrid config for '{strategy_name}'."
            )
            return RetrievalStrategyConfig(strategy_name=strategy_name)

        strategy = self._registry[strategy_name]
        # Apply task-level filters from classification.
        if classification.task_type and strategy.repository_filter is None:
            pass  # repository filter is set externally if needed

        logger.debug(
            f"Resolved strategy '{strategy_name}' for task_type={classification.task_type}"
        )
        return strategy

    def list_strategies(self) -> Dict[str, RetrievalStrategyConfig]:
        """Return all registered strategies."""
        return dict(self._registry)
