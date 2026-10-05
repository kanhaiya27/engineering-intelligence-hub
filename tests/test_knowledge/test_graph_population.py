"""
Tests for knowledge-graph population (WORK_PLAN B3): node IDs, AST extraction,
edge resolution, and — the contract that matters — that a graph built by
EngineeringGraphBuilder is reachable by GraphAugmentedRetriever.
"""

import uuid
from unittest.mock import MagicMock

import pytest

from knowledge.graph.base import NodeLabel, RelationshipType
from knowledge.graph.builder import EngineeringGraphBuilder
from knowledge.graph.extractor import ASTGraphExtractor, is_test_path
from knowledge.graph.ids import file_node_id, module_name_for_path, module_node_id
from knowledge.graph.in_memory import InMemoryGraphStore
from knowledge.schemas.artifacts import ArtifactType, SourceFile
from knowledge.schemas.tasks import RetrievalResult, RetrievedChunk
from retrieval.graph_augmented import GraphAugmentedRetriever
from retrieval.strategies import RetrievalMode, RetrievalStrategyConfig

REPO = "pallets/flask"
COMMIT = "c12a5d874c5a014495eb2db8a73f40037bc813ac"


def _source(path: str, code: str, repo: str = REPO) -> SourceFile:
    return SourceFile(
        artifact_id=f"{repo}:{path}",
        artifact_type=ArtifactType.SOURCE_CODE,
        repository=repo,
        commit_sha=COMMIT,
        source_path=path,
        raw_content=code,
        language="python",
    )


APP = """
from . import globals as g
from .helpers import url_for
import werkzeug

def make_response():
    return url_for()

class Flask:
    def run(self):
        return self.wsgi_app()

    def wsgi_app(self):
        return make_response()
"""
HELPERS = "def url_for():\n    return '/'\n"
INIT = "from .app import Flask\n"
GLOBALS = "current_app = None\n"


def _flask_like() -> list:
    return [
        _source("src/flask/__init__.py", INIT),
        _source("src/flask/app.py", APP),
        _source("src/flask/helpers.py", HELPERS),
        _source("src/flask/globals.py", GLOBALS),
    ]


# --- ids ---------------------------------------------------------------------

@pytest.mark.parametrize("path, expected", [
    ("src/flask/app.py", "flask.app"),
    ("src/flask/__init__.py", "flask"),
    ("src/flask/http.py", "flask.http"),      # rstrip(".py") used to give "flask.htt"
    ("docs/happy.py", "docs.happy"),          # ... and "docs.ha"
    ("src\\flask\\json\\tag.py", "flask.json.tag"),
    ("README.md", None),
])
def test_module_name_for_path(path, expected):
    assert module_name_for_path(path) == expected


def test_file_node_id_is_the_retriever_lookup_key():
    # GraphAugmentedRetriever builds f"file:{chunk.repository}:{chunk.source_path}".
    assert file_node_id(REPO, "src/flask/app.py") == "file:pallets/flask:src/flask/app.py"


@pytest.mark.parametrize("path, expected", [
    ("tests/test_app.py", True),
    ("testing/python/collect.py", True),
    ("examples/tutorial/tests/conftest.py", True),
    ("src/_pytest/python.py", False),         # "test" in path used to mark all of pytest
    ("src/flask/testing.py", False),
])
def test_is_test_path(path, expected):
    assert is_test_path(path) is expected


# --- extraction ----------------------------------------------------------------

def test_relative_imports_resolve_to_repository_modules():
    nodes, edges = ASTGraphExtractor().extract(_source("src/flask/app.py", APP))
    app_module = module_node_id(REPO, COMMIT, "flask.app")
    imports = {e.target_id for e in edges if e.relationship == RelationshipType.IMPORTS}
    assert module_node_id(REPO, COMMIT, "flask") in imports
    assert module_node_id(REPO, COMMIT, "flask.globals") in imports
    assert module_node_id(REPO, COMMIT, "flask.helpers") in imports
    assert all(e.source_id == app_module for e in edges if e.relationship == RelationshipType.IMPORTS)


def test_calls_resolve_only_inside_the_file():
    nodes, edges = ASTGraphExtractor().extract(_source("src/flask/app.py", APP))
    by_id = {n.node_id: n for n in nodes}
    calls = {
        (by_id[e.source_id].properties["symbol_name"], by_id[e.target_id].properties["symbol_name"])
        for e in edges if e.relationship == RelationshipType.CALLS
    }
    # self.wsgi_app() -> method; make_response() -> top-level function.
    # url_for() is defined in another file and is not guessed.
    assert calls == {("Flask.run", "Flask.wsgi_app"), ("Flask.wsgi_app", "make_response")}


# --- builder -------------------------------------------------------------------

def test_builder_persists_only_resolvable_edges_and_reports_true_counts():
    store = InMemoryGraphStore()
    metrics = EngineeringGraphBuilder(store).build_repository_graph(REPO, _flask_like(), commit_sha=COMMIT)

    assert metrics["total_nodes"] == store.count_nodes()
    assert metrics["total_edges"] == store.count_edges()
    # No placeholder nodes invented for dangling edges.
    assert all(n.label != "Unknown" for n in store._nodes.values())
    # `import werkzeug` has no node in this repository: dropped and counted.
    assert metrics["edges_dropped_unresolved"]["IMPORTS"] >= 1
    assert store.get_node(module_node_id(REPO, COMMIT, "werkzeug")) is None
    # The in-repo import is kept.
    app_imports = store.get_neighbours(module_node_id(REPO, COMMIT, "flask.app"), relationship="IMPORTS")
    assert {n.properties["symbol_name"] for _, n in app_imports} >= {"flask.helpers", "flask.globals"}


def test_built_graph_is_reachable_by_graph_augmented_retriever():
    """The B3 contract: before the ID fix, 0 graph chunks were ever injected."""
    store = InMemoryGraphStore()
    EngineeringGraphBuilder(store).build_repository_graph(REPO, _flask_like(), commit_sha=COMMIT)

    # A chunk shaped exactly as DenseRetriever returns it from the Qdrant payload.
    chunk = RetrievedChunk(
        chunk_id="c1", content="class Flask", score=0.9,
        repository=REPO, source_path="src/flask/app.py",
    )
    retriever = GraphAugmentedRetriever(graph_store=store)
    retriever._hybrid = MagicMock()
    retriever._hybrid.retrieve.return_value = RetrievalResult(
        task_id="t", strategy_used="graph_augmented", chunks=[chunk],
    )
    result = retriever.retrieve("q", RetrievalStrategyConfig(
        strategy_name="graph_augmented", mode=RetrievalMode.GRAPH_AUGMENTED,
        include_graph_context=True, graph_hop_depth=1,
    ))
    assert result.metadata["graph_chunks_injected"] > 0
    labels = {c.metadata["graph_node_label"] for c in result.chunks if c.metadata.get("graph_context")}
    assert NodeLabel.MODULE in labels


# --- Neo4j batch upserts (integration; skipped without a running Neo4j) ----------

def _neo4j_or_skip():
    from knowledge.graph.neo4j import Neo4jGraphStore
    store = Neo4jGraphStore()
    if not store.is_available():
        pytest.skip("Neo4j not reachable")
    return store


def test_neo4j_batch_build_matches_in_memory_build():
    store = _neo4j_or_skip()
    repo = f"eih-test/{uuid.uuid4().hex[:8]}"   # unique, so real graph data is never touched
    artifacts = [_source(a.source_path, a.raw_content, repo=repo) for a in _flask_like()]
    try:
        metrics = EngineeringGraphBuilder(store).build_repository_graph(repo, artifacts, commit_sha=COMMIT)
        nodes = store.query("MATCH (n:Entity {repository: $r}) RETURN count(n) AS c", {"r": repo})[0]["c"]
        edges = store.query(
            "MATCH (a:Entity {repository: $r})-[e]->(b:Entity {repository: $r}) RETURN count(e) AS c",
            {"r": repo},
        )[0]["c"]
        assert nodes == metrics["total_nodes"]
        assert edges == metrics["total_edges"]
        assert store.get_node(file_node_id(repo, "src/flask/app.py")) is not None

        memory = InMemoryGraphStore()
        reference = EngineeringGraphBuilder(memory).build_repository_graph(repo, artifacts, commit_sha=COMMIT)
        assert (nodes, edges) == (reference["total_nodes"], reference["total_edges"])
    finally:
        store.query("MATCH (n:Entity {repository: $r}) DETACH DELETE n", {"r": repo})
        store.disconnect()
