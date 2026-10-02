"""
Tests for M3 Adaptive Retrieval
================================
Tests cover:
  - AdaptiveRetrievalPolicy: task_type and criticality resolution
  - GraphAugmentedRetriever: baseline without graph store (graceful degradation)
  - GraphAugmentedRetriever: graph context injection with mock graph store
  - AdaptiveRetrievalPipeline: all three experiment modes
  - RetrievalRouter: YAML strategy loading
  - retrieval.yaml: all new strategies are parseable
"""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple
from unittest.mock import MagicMock


from knowledge.graph.base import BaseGraphStore, GraphEdge, GraphNode, NodeLabel
from knowledge.schemas.tasks import (
    ComplexityLevel,
    CriticalityLevel,
    RetrievedChunk,
    RetrievalResult,
    SDLCStage,
    TaskClassification,
    TaskType,
)
from retrieval.adaptive import AdaptiveRetrievalPipeline, ExperimentMode
from retrieval.graph_augmented import GraphAugmentedRetriever
from retrieval.policy import (
    AdaptiveRetrievalPolicy,
    _TASK_TYPE_STRATEGY_MAP,
)
from retrieval.router import RetrievalRouter
from retrieval.strategies import RetrievalMode, RetrievalStrategyConfig


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_classification(
    task_type: str = TaskType.CODE_EXPLANATION,
    criticality: str = CriticalityLevel.MEDIUM,
    task_id: str = "test-001",
) -> TaskClassification:
    return TaskClassification(
        task_id=task_id,
        task_type=task_type,
        sdlc_stage=SDLCStage.DEVELOPMENT,
        complexity=ComplexityLevel.MEDIUM,
        criticality=criticality,
        security_sensitivity="none",
        quality_threshold=0.7,
    )


def _make_registry(*names: str) -> Dict[str, RetrievalStrategyConfig]:
    """Build a minimal strategy registry for testing."""
    registry = {}
    for name in names:
        include_graph = "graph" in name
        mode = (
            RetrievalMode.GRAPH_AUGMENTED if include_graph
            else (RetrievalMode.SPARSE if "sparse" in name else RetrievalMode.HYBRID)
        )
        registry[name] = RetrievalStrategyConfig(
            strategy_name=name,
            mode=mode,
            top_k=5,
            include_graph_context=include_graph,
            graph_hop_depth=1,
        )
    return registry


def _make_chunk(chunk_id: str = "chunk-1", source_path: str = "src/app.py") -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id=chunk_id,
        content="def authenticate(): ...",
        source_path=source_path,
        score=0.85,
        repository="flask",
        metadata={"start_line": 10, "end_line": 20},
    )


def _make_retrieval_result(chunks=None) -> RetrievalResult:
    return RetrievalResult(
        task_id="test-001",
        strategy_used="hybrid",
        chunks=chunks or [_make_chunk()],
        total_retrieved=1,
        retrieval_latency_ms=12.0,
        metadata={"mode": "hybrid"},
    )


class MockGraphStore(BaseGraphStore):
    """Minimal in-memory graph store for testing."""

    def __init__(self) -> None:
        self._nodes: Dict[str, GraphNode] = {}
        self._edges: List[GraphEdge] = []

    @property
    def store_name(self) -> str:
        return "mock_graph"

    def connect(self) -> None:
        pass

    def disconnect(self) -> None:
        pass

    def upsert_node(self, node: GraphNode) -> str:
        self._nodes[node.node_id] = node
        return node.node_id

    def upsert_edge(self, edge: GraphEdge) -> None:
        self._edges.append(edge)

    def get_node(self, node_id: str, label: Optional[str] = None) -> Optional[GraphNode]:
        return self._nodes.get(node_id)

    def get_neighbours(
        self,
        node_id: str,
        relationship: Optional[str] = None,
        direction: str = "outbound",
        max_depth: int = 1,
    ) -> List[Tuple[GraphEdge, GraphNode]]:
        results = []
        for edge in self._edges:
            if direction in ("outbound", "both") and edge.source_id == node_id:
                target = self._nodes.get(edge.target_id)
                if target and (relationship is None or edge.relationship == relationship):
                    results.append((edge, target))
            if direction in ("inbound", "both") and edge.target_id == node_id:
                source = self._nodes.get(edge.source_id)
                if source and (relationship is None or edge.relationship == relationship):
                    results.append((edge, source))
        return results

    def query(self, query_string: str, parameters: Optional[Dict] = None) -> List[Dict]:
        return []

    def delete_node(self, node_id: str) -> bool:
        existed = node_id in self._nodes
        self._nodes.pop(node_id, None)
        return existed

    def count_nodes(self, label: Optional[str] = None) -> int:
        if label is None:
            return len(self._nodes)
        return sum(1 for n in self._nodes.values() if n.label == label)

    def count_edges(self, relationship: Optional[str] = None) -> int:
        if relationship is None:
            return len(self._edges)
        return sum(1 for e in self._edges if e.relationship == relationship)


# ---------------------------------------------------------------------------
# 1. AdaptiveRetrievalPolicy
# ---------------------------------------------------------------------------

class TestAdaptiveRetrievalPolicy:

    def test_policy_map_is_complete(self):
        """All 21 TaskType values (excluding UNKNOWN) should be in the policy map."""
        all_task_types = [t for t in TaskType if t != TaskType.UNKNOWN]
        missing = [t for t in all_task_types if t not in _TASK_TYPE_STRATEGY_MAP]
        assert not missing, f"Task types missing from policy map: {missing}"

    def test_resolve_code_explanation_returns_hybrid(self):
        registry = _make_registry("hybrid", "dense", "dense_fast", "graph_augmented")
        policy = AdaptiveRetrievalPolicy(registry)
        clf = _make_classification(task_type=TaskType.CODE_EXPLANATION)
        result = policy.resolve(clf)
        assert result.strategy_name == "hybrid"

    def test_resolve_architecture_qa_returns_graph_augmented(self):
        registry = _make_registry("hybrid", "graph_augmented")
        policy = AdaptiveRetrievalPolicy(registry)
        clf = _make_classification(task_type=TaskType.ARCHITECTURE_QA)
        result = policy.resolve(clf)
        assert result.strategy_name == "graph_augmented"

    def test_criticality_critical_escalates_to_graph_reranked(self):
        registry = _make_registry(
            "hybrid", "graph_augmented", "graph_augmented_reranked", "hybrid_reranked"
        )
        # Need the actual reranked strategy
        registry["graph_augmented_reranked"] = RetrievalStrategyConfig(
            strategy_name="graph_augmented_reranked",
            mode=RetrievalMode.GRAPH_AUGMENTED,
            include_graph_context=True,
            enable_reranking=True,
        )
        policy = AdaptiveRetrievalPolicy(registry)
        clf = _make_classification(criticality=CriticalityLevel.CRITICAL)
        result = policy.resolve(clf)
        assert result.strategy_name == "graph_augmented_reranked"

    def test_criticality_high_escalates_to_hybrid_reranked(self):
        registry = _make_registry("hybrid", "hybrid_reranked")
        registry["hybrid_reranked"] = RetrievalStrategyConfig(
            strategy_name="hybrid_reranked",
            mode=RetrievalMode.HYBRID,
            enable_reranking=True,
        )
        policy = AdaptiveRetrievalPolicy(registry)
        clf = _make_classification(
            task_type=TaskType.CODE_EXPLANATION,
            criticality=CriticalityLevel.HIGH,
        )
        result = policy.resolve(clf)
        assert result.strategy_name == "hybrid_reranked"

    def test_explicit_override_takes_precedence(self):
        registry = _make_registry("hybrid", "dense_fast")
        policy = AdaptiveRetrievalPolicy(registry)
        clf = _make_classification(task_type=TaskType.ARCHITECTURE_QA)
        result = policy.resolve(clf, override_strategy_name="dense_fast")
        assert result.strategy_name == "dense_fast"

    def test_missing_strategy_falls_back_to_hybrid(self):
        registry = _make_registry("hybrid")
        policy = AdaptiveRetrievalPolicy(registry)
        clf = _make_classification(task_type=TaskType.ARCHITECTURE_QA)
        # graph_augmented not in registry → should fall back to hybrid
        result = policy.resolve(clf)
        assert result.strategy_name == "hybrid"

    def test_unknown_override_falls_back_to_hybrid(self):
        registry = _make_registry("hybrid")
        policy = AdaptiveRetrievalPolicy(registry)
        clf = _make_classification()
        result = policy.resolve(clf, override_strategy_name="nonexistent_strategy_xyz")
        assert result.strategy_name == "hybrid"

    def test_list_policies_returns_dict(self):
        policy = AdaptiveRetrievalPolicy({})
        p = policy.list_policies()
        assert isinstance(p, dict)
        assert TaskType.ARCHITECTURE_QA in p

    def test_incident_retrieval_maps_to_incident_sparse(self):
        registry = _make_registry("hybrid", "incident_sparse")
        policy = AdaptiveRetrievalPolicy(registry)
        clf = _make_classification(task_type=TaskType.INCIDENT_RETRIEVAL)
        result = policy.resolve(clf)
        assert result.strategy_name == "incident_sparse"


# ---------------------------------------------------------------------------
# 2. GraphAugmentedRetriever — graceful degradation
# ---------------------------------------------------------------------------

class TestGraphAugmentedRetrieverDegradation:
    """Without a graph store, should behave exactly like HybridRetriever."""

    def _make_retriever_with_mock(self, graph_store=None):
        """Build a GraphAugmentedRetriever with mocked internal hybrid retriever."""
        retriever = object.__new__(GraphAugmentedRetriever)
        mock_hybrid = MagicMock()
        mock_hybrid.retrieve.return_value = _make_retrieval_result()
        retriever._hybrid = mock_hybrid
        retriever._graph_store = graph_store
        return retriever

    def test_retrieve_without_graph_store_returns_hybrid_result(self):
        retriever = self._make_retriever_with_mock(graph_store=None)
        strategy = RetrievalStrategyConfig(
            strategy_name="graph_augmented",
            mode=RetrievalMode.GRAPH_AUGMENTED,
            include_graph_context=True,
            graph_hop_depth=1,
        )
        clf = _make_classification()
        result = retriever.retrieve(
            query="What does authenticate() do?",
            strategy=strategy,
            classification=clf,
        )
        # Graph augmentation was requested but no graph store → should still return
        assert result.total_retrieved >= 1
        assert result.metadata.get("graph_augmented") is False
        assert result.metadata.get("graph_chunks_injected") == 0

    def test_retrieve_without_graph_context_flag_skips_expansion(self):
        retriever = self._make_retriever_with_mock(graph_store=None)
        strategy = RetrievalStrategyConfig(
            strategy_name="hybrid",
            mode=RetrievalMode.HYBRID,
            include_graph_context=False,
        )
        clf = _make_classification()
        result = retriever.retrieve(query="test", strategy=strategy, classification=clf)
        assert result.metadata.get("graph_augmented") is False

    def test_retriever_name(self):
        retriever = object.__new__(GraphAugmentedRetriever)
        retriever._hybrid = MagicMock()
        retriever._graph_store = None
        assert retriever.retriever_name == "graph_augmented"


# ---------------------------------------------------------------------------
# 3. GraphAugmentedRetriever — with mock graph store
# ---------------------------------------------------------------------------

class TestGraphAugmentedRetrieverWithGraph:

    def _make_retriever_with_graph(self, store: MockGraphStore) -> GraphAugmentedRetriever:
        """Build GraphAugmentedRetriever with mock internals to avoid torch."""
        retriever = object.__new__(GraphAugmentedRetriever)
        retriever._hybrid = MagicMock()
        retriever._hybrid.retrieve.return_value = _make_retrieval_result(chunks=[_make_chunk()])
        retriever._graph_store = store
        return retriever

    def _build_graph_store(self) -> MockGraphStore:
        store = MockGraphStore()
        # Add a file node that matches our test chunk's source_path
        file_node = GraphNode(
            node_id="file:flask:src/app.py",
            label=NodeLabel.FILE,
            properties={
                "path": "src/app.py",
                "repository": "flask",
                "name": "app.py",
            },
        )
        func_node = GraphNode(
            node_id="func:flask:abc123:src/app.py:authenticate:10",
            label=NodeLabel.FUNCTION,
            properties={
                "name": "authenticate",
                "path": "src/app.py",
                "repository": "flask",
                "start_line": 10,
                "end_line": 25,
                "commit_sha": "abc123",
            },
        )
        store.upsert_node(file_node)
        store.upsert_node(func_node)
        store.upsert_edge(GraphEdge(
            source_id=file_node.node_id,
            target_id=func_node.node_id,
            relationship="CONTAINS",
            properties={"depth": 1},
        ))
        return store

    def test_graph_context_injected_when_store_available(self):
        store = self._build_graph_store()
        retriever = self._make_retriever_with_graph(store)

        strategy = RetrievalStrategyConfig(
            strategy_name="graph_augmented",
            mode=RetrievalMode.GRAPH_AUGMENTED,
            include_graph_context=True,
            graph_hop_depth=1,
            max_context_chunks=5,
        )
        clf = _make_classification()

        result = retriever.retrieve(
            query="What does authenticate() do?",
            strategy=strategy,
            classification=clf,
        )
        assert result.metadata.get("graph_augmented") is True
        assert result.metadata.get("graph_chunks_injected") >= 1

        # Graph context chunks should be labelled correctly
        graph_chunks = [c for c in result.chunks if c.metadata.get("graph_context")]
        assert len(graph_chunks) >= 1
        assert graph_chunks[0].metadata["graph_node_label"] == NodeLabel.FUNCTION

    def test_graph_chunk_content_contains_expected_fields(self):
        store = self._build_graph_store()
        retriever = self._make_retriever_with_graph(store)
        strategy = RetrievalStrategyConfig(
            strategy_name="graph_augmented",
            mode=RetrievalMode.GRAPH_AUGMENTED,
            include_graph_context=True,
        )
        clf = _make_classification()
        result = retriever.retrieve(query="test", strategy=strategy, classification=clf)
        graph_chunks = [c for c in result.chunks if c.metadata.get("graph_context")]
        assert any("GRAPH_CONTEXT" in gc.content for gc in graph_chunks)
        assert any("authenticate" in gc.content for gc in graph_chunks)

    def test_graph_expansion_bounds_respected(self):
        """Graph chunks must never exceed _HEURISTIC_MAX_GRAPH_CHUNKS."""
        from retrieval.graph_augmented import _HEURISTIC_MAX_GRAPH_CHUNKS
        store = MockGraphStore()
        file_node = GraphNode("file:flask:src/app.py", NodeLabel.FILE, {"path": "src/app.py"})
        store.upsert_node(file_node)

        # Add many neighbour nodes (beyond the bound)
        for i in range(_HEURISTIC_MAX_GRAPH_CHUNKS + 5):
            n = GraphNode(
                f"func:flask:sha:src/app.py:fn{i}:{i}",
                NodeLabel.FUNCTION,
                {"name": f"fn{i}", "path": "src/app.py", "start_line": i, "end_line": i + 5},
            )
            store.upsert_node(n)
            store.upsert_edge(GraphEdge(
                source_id=file_node.node_id,
                target_id=n.node_id,
                relationship="CONTAINS",
                properties={"depth": 1},
            ))

        retriever = self._make_retriever_with_graph(store)
        strategy = RetrievalStrategyConfig(
            strategy_name="graph_augmented",
            mode=RetrievalMode.GRAPH_AUGMENTED,
            include_graph_context=True,
        )
        result = retriever.retrieve(query="test", strategy=strategy)

        graph_chunks = [c for c in result.chunks if c.metadata.get("graph_context")]
        assert len(graph_chunks) <= _HEURISTIC_MAX_GRAPH_CHUNKS


# ---------------------------------------------------------------------------
# 4. AdaptiveRetrievalPipeline — experiment modes
# ---------------------------------------------------------------------------

class TestAdaptiveRetrievalPipeline:

    def _make_pipeline(self) -> AdaptiveRetrievalPipeline:
        """Create a pipeline with offline registry (no YAML file needed)."""
        pipeline = AdaptiveRetrievalPipeline.__new__(AdaptiveRetrievalPipeline)
        registry = _make_registry(
            "hybrid", "dense", "dense_fast", "sparse",
            "graph_augmented", "graph_augmented_reranked",
            "hybrid_reranked", "hybrid_bm25",
            "incident_sparse", "incident_graph",
        )
        from retrieval.policy import AdaptiveRetrievalPolicy
        pipeline._registry = registry
        pipeline._policy = AdaptiveRetrievalPolicy(registry)
        pipeline._graph_store = None
        pipeline._dense = MagicMock()
        pipeline._sparse = MagicMock()
        pipeline._hybrid = MagicMock()
        pipeline._graph_aug = MagicMock()
        pipeline._router = MagicMock()
        pipeline._router.list_strategies.return_value = registry
        return pipeline

    def _setup_mock_retriever(self, mock_retriever) -> None:
        mock_retriever.retrieve.return_value = _make_retrieval_result()

    def test_baseline_b_uses_hybrid(self):
        pipeline = self._make_pipeline()
        self._setup_mock_retriever(pipeline._hybrid)
        clf = _make_classification()
        result = pipeline.retrieve(
            query="test",
            classification=clf,
            experiment_mode=ExperimentMode.BASELINE_B,
        )
        pipeline._hybrid.retrieve.assert_called_once()
        pipeline._graph_aug.retrieve.assert_not_called()
        assert result.metadata.get("experiment_mode") == ExperimentMode.BASELINE_B

    def test_system_c_no_graph_augmentation(self):
        pipeline = self._make_pipeline()
        # system_c should never call graph_aug
        self._setup_mock_retriever(pipeline._hybrid)
        self._setup_mock_retriever(pipeline._graph_aug)
        clf = _make_classification(task_type=TaskType.ARCHITECTURE_QA)
        result = pipeline.retrieve(
            query="test",
            classification=clf,
            experiment_mode=ExperimentMode.SYSTEM_C,
        )
        pipeline._graph_aug.retrieve.assert_not_called()
        assert result.metadata.get("experiment_mode") == ExperimentMode.SYSTEM_C

    def test_system_d_can_use_graph_aug(self):
        pipeline = self._make_pipeline()
        self._setup_mock_retriever(pipeline._graph_aug)
        self._setup_mock_retriever(pipeline._hybrid)
        clf = _make_classification(task_type=TaskType.ARCHITECTURE_QA)
        # graph_augmented strategy has include_graph_context=True
        pipeline.retrieve(
            query="What are the dependencies?",
            classification=clf,
            experiment_mode=ExperimentMode.SYSTEM_D,
        )
        # graph_aug should have been called for architecture tasks in SYSTEM_D
        pipeline._graph_aug.retrieve.assert_called_once()

    def test_override_strategy_name_respected(self):
        pipeline = self._make_pipeline()
        # Add a proper DENSE mode strategy to the registry
        from retrieval.strategies import RetrievalMode
        pipeline._registry["dense"] = RetrievalStrategyConfig(
            strategy_name="dense",
            mode=RetrievalMode.DENSE,
            top_k=5,
            include_graph_context=False,
        )
        pipeline._policy = AdaptiveRetrievalPolicy(pipeline._registry)
        self._setup_mock_retriever(pipeline._dense)
        self._setup_mock_retriever(pipeline._hybrid)
        clf = _make_classification()
        pipeline.retrieve(
            query="test",
            classification=clf,
            experiment_mode=ExperimentMode.SYSTEM_D,
            override_strategy_name="dense",
        )
        # dense strategy has include_graph_context=False and mode=DENSE
        # → should route to _dense, not _graph_aug
        pipeline._dense.retrieve.assert_called_once()
        pipeline._graph_aug.retrieve.assert_not_called()

    def test_result_contains_experiment_metadata(self):
        pipeline = self._make_pipeline()
        self._setup_mock_retriever(pipeline._hybrid)
        clf = _make_classification()
        result = pipeline.retrieve(
            query="test",
            classification=clf,
            experiment_mode=ExperimentMode.SYSTEM_C,
        )
        assert "experiment_mode" in result.metadata
        assert "task_type" in result.metadata
        assert "criticality" in result.metadata


# ---------------------------------------------------------------------------
# 5. Strategy YAML integrity
# ---------------------------------------------------------------------------

class TestRetrievalYAML:

    def test_yaml_loads_all_new_strategies(self):
        """All M3 strategies must be parseable from the YAML file."""
        router = RetrievalRouter.from_yaml("configs/retrieval.yaml")
        registry = router.list_strategies()
        required_strategies = [
            "dense", "dense_fast", "sparse", "hybrid", "hybrid_reranked",
            "graph_augmented", "graph_augmented_reranked",
            "hybrid_bm25", "incident_sparse", "incident_graph",
        ]
        for name in required_strategies:
            assert name in registry, f"Strategy '{name}' missing from configs/retrieval.yaml"

    def test_incident_graph_has_graph_context_enabled(self):
        router = RetrievalRouter.from_yaml("configs/retrieval.yaml")
        registry = router.list_strategies()
        incident_graph = registry["incident_graph"]
        assert incident_graph.include_graph_context is True
        assert incident_graph.sparse_weight > incident_graph.dense_weight

    def test_hybrid_bm25_is_sparse_dominant(self):
        router = RetrievalRouter.from_yaml("configs/retrieval.yaml")
        registry = router.list_strategies()
        hb = registry["hybrid_bm25"]
        assert hb.sparse_weight > hb.dense_weight

    def test_all_strategies_have_valid_modes(self):
        router = RetrievalRouter.from_yaml("configs/retrieval.yaml")
        valid_modes = {m.value for m in RetrievalMode}
        for name, cfg in router.list_strategies().items():
            assert cfg.mode in valid_modes, f"Strategy '{name}' has invalid mode '{cfg.mode}'"
