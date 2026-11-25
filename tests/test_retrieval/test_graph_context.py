"""System D's graph step: relations stated, other files first, co-change included, hubs not crossed."""

from __future__ import annotations

from unittest.mock import MagicMock

from knowledge.graph.base import GraphEdge, GraphNode, NodeLabel
from knowledge.graph.builder import EngineeringGraphBuilder
from knowledge.graph.extractor import commit_node_id, file_node_id
from knowledge.graph.in_memory import InMemoryGraphStore
from knowledge.schemas.tasks import RetrievalResult, RetrievedChunk
from retrieval.graph_augmented import GraphAugmentedRetriever
from retrieval.strategies import RetrievalMode, RetrievalStrategyConfig

REPO = "pallets/flask"
FILES = [
    ("src/flask/app.py", "from .ctx import AppContext\n\n\ndef make():\n    return AppContext()\n"),
    ("src/flask/ctx.py", "class AppContext:\n    def push(self):\n        return 1\n"),
    ("src/flask/json.py", "def dumps(x):\n    return str(x)\n"),
    ("tests/test_ctx.py", "from flask.ctx import AppContext\n\n\ndef test_push():\n    AppContext().push()\n"),
]


def retriever_for(store):
    r = object.__new__(GraphAugmentedRetriever)
    r._graph_store = store
    r._hybrid = MagicMock()
    r._hybrid.retrieve.return_value = RetrievalResult(task_id="t", strategy_used="g", chunks=[RetrievedChunk(
        chunk_id="c1", content="class AppContext: ...", score=0.9, repository=REPO, source_path="src/flask/ctx.py",
        metadata={"start_line": 1, "end_line": 3})], total_retrieved=1)
    return r


def test_graph_chunks_state_the_relation_and_prefer_other_files():
    store = InMemoryGraphStore()
    EngineeringGraphBuilder(store).build_repository_graph(REPO, "c12a5d8", FILES)
    for sha in ("s1", "s2"):
        cid = commit_node_id(REPO, sha)
        store.upsert_node(GraphNode(cid, NodeLabel.COMMIT))
        for p in ("src/flask/ctx.py", "src/flask/json.py"):
            store.upsert_edge(GraphEdge(cid, file_node_id(REPO, p), "MODIFIES"))

    strategy = RetrievalStrategyConfig(strategy_name="g", mode=RetrievalMode.GRAPH_AUGMENTED,
                                       include_graph_context=True, graph_hop_depth=2, max_context_chunks=5)
    result = retriever_for(store).retrieve(query="how is the app context pushed?", strategy=strategy)
    graph = [c for c in result.chunks if c.metadata.get("graph_context")]
    relations = [c.metadata["graph_relation"] for c in graph]
    assert relations[0] == "TESTS", "a test file of the retrieved file is the most useful neighbour"
    assert "tests/test_ctx.py --TESTS--> src/flask/ctx.py" in graph[0].content
    assert "CO_CHANGED" in relations
    co = next(c for c in graph if c.metadata["graph_relation"] == "CO_CHANGED")
    assert "changed together in 2 commits" in co.content and co.source_path == "src/flask/json.py"
    assert result.metadata["graph_chunks_injected"] == len(graph) <= 4


def test_augment_keeps_base_chunks_and_appends_graph_context():
    """System D (C23): C's chunks unchanged and first; graph context appended after them."""
    store = InMemoryGraphStore()
    EngineeringGraphBuilder(store).build_repository_graph(REPO, "c12a5d8", FILES)
    r = retriever_for(store)
    base = r._hybrid.retrieve.return_value
    out = r.augment(base.model_copy(deep=True), hop_depth=2, task_id="t")
    assert [c.chunk_id for c in out.chunks[:1]] == [c.chunk_id for c in base.chunks]
    graph = out.chunks[1:]
    assert graph and all(c.metadata.get("graph_context") for c in graph)
    assert out.metadata["graph_augmented"] is True and out.metadata["graph_hop_depth"] == 2
    r._hybrid.retrieve.assert_not_called()  # augment never re-retrieves


def test_augment_without_store_returns_base_unchanged():
    r = retriever_for(None)
    base = r._hybrid.retrieve.return_value
    out = r.augment(base, hop_depth=2)
    assert out.chunks == base.chunks and out.metadata["graph_augmented"] is False
