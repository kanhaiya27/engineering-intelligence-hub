"""
Engineering Intelligence Hub — Adaptive Retrieval Pipeline (M3)
================================================================
Wraps classification → policy → strategy → retriever routing in one
callable interface. This is the MAIN ENTRY POINT for Phase-2 retrieval.

Experiment modes supported:
  - Baseline B : Fixed RAG (HybridRetriever, strategy="hybrid")
  - System C   : Task-aware retrieval, no graph (dense/hybrid/sparse per task)
  - System D   : Task-aware graph-augmented retrieval (GraphAugmentedRetriever)

  Mode is selected by `experiment_mode` argument to `retrieve()`.

Backward Compatibility:
  Phase-1 callers that invoke HybridRetriever.retrieve() directly are
  UNAFFECTED. This module adds a HIGHER-LEVEL abstraction on top of
  Phase-1 retrievers.

IMPORTANT RESEARCH NOTE:
  All mode-to-strategy mappings are INITIAL HEURISTIC configurations
  for the experiment baseline.  No energy, latency or quality claims
  are made until Phase-2 M5 controlled evaluation is complete.
"""

from __future__ import annotations

import time
from enum import Enum
from typing import TYPE_CHECKING, Dict, Optional

from core.config import settings
from core.logging import get_logger
from knowledge.graph.base import BaseGraphStore
from knowledge.schemas.tasks import RetrievalResult, TaskClassification
from retrieval.policy import AdaptiveRetrievalPolicy
from retrieval.router import RetrievalRouter
from retrieval.strategies import RetrievalMode, RetrievalStrategyConfig

if TYPE_CHECKING:
    pass

logger = get_logger(__name__)

# Default YAML path for strategy registry
_DEFAULT_YAML_PATH = "configs/retrieval.yaml"


class ExperimentMode(str, Enum):
    """
    Controlled experiment modes for Phase-2 ablation.

    BASELINE_B : Phase-1 fixed hybrid RAG (no adaptation)
    SYSTEM_C   : Adaptive dense/hybrid/sparse per task type (no graph)
    SYSTEM_D   : Full adaptive retrieval with graph augmentation
    """
    BASELINE_B = "baseline_b"  # Fixed hybrid RAG
    SYSTEM_C = "system_c"      # Task-aware, no graph
    SYSTEM_D = "system_d"      # Task-aware + graph augmented


class AdaptiveRetrievalPipeline:
    """
    Task-aware adaptive retrieval pipeline for Phase-2.

    Wires together:
      1. RetrievalRouter  — resolves strategy_name from TaskClassification
      2. AdaptiveRetrievalPolicy — task_type → strategy override logic
      3. GraphAugmentedRetriever — executes graph-augmented hybrid retrieval
      4. HybridRetriever  — executes fixed hybrid retrieval (Baseline B)
    """

    def __init__(
        self,
        graph_store: Optional[BaseGraphStore] = None,
        strategy_yaml_path: str = _DEFAULT_YAML_PATH,
    ) -> None:
        # Load strategy registry from YAML (raises on missing file only when
        # YAML is available, otherwise creates an empty router for offline tests)
        self._router = self._load_router(strategy_yaml_path)
        self._registry = self._router.list_strategies()
        self._policy = AdaptiveRetrievalPolicy(strategy_registry=self._registry)
        self._graph_store = graph_store

        # Lazy-import concrete retrievers to avoid pulling torch/qdrant into
        # modules that only use retrieval.strategies or retrieval.policy.
        from retrieval.bm25 import BM25Retriever
        from retrieval.dense import DenseRetriever
        from retrieval.graph_augmented import GraphAugmentedRetriever
        from retrieval.hybrid import HybridRetriever

        # Initialise retrievers (construction is cheap; connections are lazy).
        #
        # BM25 is pointed at the SAME store and collection the dense retriever
        # uses, so both halves of hybrid retrieval are guaranteed to index one
        # corpus. Without this the sparse index stays empty and every "hybrid"
        # result is silently dense-only. The load itself is lazy — it happens on
        # first retrieval, not here.
        self._dense = DenseRetriever()
        self._sparse = BM25Retriever(
            vector_store=self._dense.vector_store,
            collection_name=self._dense.collection_name,
            autoload=True,
        )
        self._hybrid = HybridRetriever(
            dense_retriever=self._dense,
            sparse_retriever=self._sparse,
        )
        self._graph_aug = GraphAugmentedRetriever(
            dense_retriever=self._dense,
            sparse_retriever=self._sparse,
            graph_store=graph_store,
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def retrieve(
        self,
        query: str,
        classification: TaskClassification,
        experiment_mode: ExperimentMode = ExperimentMode.SYSTEM_D,
        override_strategy_name: Optional[str] = None,
        task_id: str = "adhoc",
        override_strategy: Optional[RetrievalStrategyConfig] = None,
    ) -> RetrievalResult:
        """
        Execute adaptive retrieval for a classified engineering task.

        Parameters
        ----------
        query : str
            The user's engineering query.
        classification : TaskClassification
            Output from M1 task intelligence.
        experiment_mode : ExperimentMode
            Controls retrieval behaviour (ablation modes).
        override_strategy_name : str, optional
            Force a specific strategy by name (ablation experiments). The name
            must be in the registry; an unknown name raises
            InvalidRetrievalStrategyError instead of silently running "hybrid".
        task_id : str
            Unique task ID for logging and correlation.
        override_strategy : RetrievalStrategyConfig, optional
            Run exactly this config, bypassing the registry. Used for escalated
            strategies (``*_esc1``, ``*_esc2_graph``, ``*_esc_max``), which are
            built at run time and are never registered. Takes precedence over
            ``override_strategy_name``.

        Returns
        -------
        RetrievalResult
        """
        start_time = time.perf_counter()

        if experiment_mode == ExperimentMode.BASELINE_B:
            # Fixed hybrid: Phase-1 behaviour, no adaptation
            strategy = self._get_fixed_hybrid_strategy()
            result = self._hybrid.retrieve(
                query=query,
                strategy=strategy,
                classification=classification,
                task_id=task_id,
            )
            result.metadata["experiment_mode"] = ExperimentMode.BASELINE_B
            return result

        # Resolve strategy: an explicit config runs as given; otherwise the
        # adaptive policy resolves a registered one.
        if override_strategy is not None:
            strategy = override_strategy
        else:
            strategy = self._policy.resolve(
                classification=classification,
                override_strategy_name=override_strategy_name,
            )

        if experiment_mode == ExperimentMode.SYSTEM_C:
            # Task-aware, no graph: strip graph_context flag
            strategy = strategy.model_copy(
                update={"include_graph_context": False}
            )
            result = self._route_to_retriever(
                query=query,
                strategy=strategy,
                classification=classification,
                task_id=task_id,
                use_graph=False,
            )
            result.metadata["experiment_mode"] = ExperimentMode.SYSTEM_C

        else:  # SYSTEM_D — full adaptive with graph augmentation
            result = self._route_to_retriever(
                query=query,
                strategy=strategy,
                classification=classification,
                task_id=task_id,
                use_graph=True,
            )
            result.metadata["experiment_mode"] = ExperimentMode.SYSTEM_D

        result.metadata["resolved_strategy"] = strategy.strategy_name
        # What the retriever was actually given, so escalation can be verified
        # as executing rather than only as named.
        result.metadata["executed_strategy"] = {
            "strategy_name": strategy.strategy_name,
            "mode": str(getattr(strategy.mode, "value", strategy.mode)),
            "top_k": strategy.top_k,
            "max_context_chunks": strategy.max_context_chunks,
            "include_graph_context": strategy.include_graph_context,
            "enable_reranking": strategy.enable_reranking,
            "reranker_type": str(getattr(strategy.reranker_type, "value", strategy.reranker_type)),
        }
        result.metadata["task_type"] = classification.task_type
        result.metadata["criticality"] = classification.criticality

        return result

    def resolve_strategy(self, classification: TaskClassification) -> RetrievalStrategyConfig:
        """The registered strategy the adaptive policy picks for a classification (attempt 0)."""
        return self._policy.resolve(classification=classification, override_strategy_name=None)

    def list_strategies(self) -> Dict[str, RetrievalStrategyConfig]:
        """Return the strategy registry for inspection / API exposure."""
        return self._router.list_strategies()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _route_to_retriever(
        self,
        query: str,
        strategy: RetrievalStrategyConfig,
        classification: TaskClassification,
        task_id: str,
        use_graph: bool,
    ) -> RetrievalResult:
        """Route to the correct retriever based on mode and strategy."""
        mode = strategy.mode

        if use_graph and strategy.include_graph_context:
            return self._graph_aug.retrieve(
                query=query,
                strategy=strategy,
                classification=classification,
                task_id=task_id,
            )
        elif mode == RetrievalMode.DENSE:
            return self._dense.retrieve(
                query=query,
                strategy=strategy,
                classification=classification,
                task_id=task_id,
            )
        elif mode == RetrievalMode.SPARSE:
            return self._sparse.retrieve(
                query=query,
                strategy=strategy,
                classification=classification,
                task_id=task_id,
            )
        else:  # HYBRID / GRAPH_AUGMENTED without graph active
            return self._hybrid.retrieve(
                query=query,
                strategy=strategy,
                classification=classification,
                task_id=task_id,
            )

    def _get_fixed_hybrid_strategy(self) -> RetrievalStrategyConfig:
        """Return the Phase-1 fixed hybrid strategy (Baseline B)."""
        if "hybrid" in self._registry:
            return self._registry["hybrid"]
        return RetrievalStrategyConfig(
            strategy_name="hybrid",
            mode=RetrievalMode.HYBRID,
            top_k=settings.retrieval.default_top_k,
        )

    @staticmethod
    def _load_router(yaml_path: str) -> RetrievalRouter:
        try:
            return RetrievalRouter.from_yaml(yaml_path)
        except FileNotFoundError:
            logger.warning(
                f"Strategy YAML '{yaml_path}' not found. "
                "Initialising empty registry (offline / test mode)."
            )
            return RetrievalRouter()
