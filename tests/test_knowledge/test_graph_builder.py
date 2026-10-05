"""Graph builder + store traversal: persisted counts, history artifacts, hub-free expansion, co-change."""

from __future__ import annotations

from knowledge.graph.base import GraphEdge, GraphNode, NodeLabel, RelationshipType as R
from knowledge.graph.builder import EngineeringGraphBuilder
from knowledge.graph.extractor import commit_node_id, file_node_id
from knowledge.graph.in_memory import InMemoryGraphStore
from knowledge.schemas.artifacts import ArtifactType, Commit, Issue, PullRequest

REPO = "pallets/flask"
FILES = [
    ("src/flask/app.py", "from .ctx import AppContext\n\n\ndef make():\n    return AppContext()\n"),
    ("src/flask/ctx.py", "class AppContext:\n    def push(self):\n        return 1\n"),
    ("src/flask/json.py", "def dumps(x):\n    return str(x)\n"),
    ("tests/test_ctx.py", "from flask.ctx import AppContext\n\n\ndef test_push():\n    AppContext().push()\n"),
]


def build():
    store = InMemoryGraphStore()
    builder = EngineeringGraphBuilder(store)
    report = builder.build_repository_graph(REPO, "c12a5d8", FILES)
    return store, builder, report


def test_report_counts_match_the_store():
    store, _, report = build()
    assert report["nodes_written"] == store.count_nodes() and report["edges_written"] == store.count_edges()
    assert report["files"] == 4 and report["edges_dropped_unresolved"] >= 0


def test_history_artifacts_link_to_the_same_file_nodes():
    store, builder, _ = build()
    commit = Commit(artifact_id="c1", artifact_type=ArtifactType.COMMIT, repository=REPO, sha="4aa68d5",
                    author_name="A", message="fix ctx push", committed_at="2024-01-01T00:00:00Z",
                    files_changed=["src/flask/ctx.py", "src/flask/gone.py"], insertions=1, deletions=1)
    issue = Issue(artifact_id="i1", artifact_type=ArtifactType.ISSUE, repository=REPO, issue_number=123,
                  title="ctx bug", author="u", resolved_by_commit="4aa68d5", linked_pull_requests=["456"])
    pr = PullRequest(artifact_id="p1", artifact_type=ArtifactType.PULL_REQUEST, repository=REPO, pr_number=456,
                     title="Fix ctx", author="u", merge_commit_sha="4aa68d5", files_changed=["src/flask/ctx.py"])
    rep = builder.build_history_graph([commit, issue, pr])
    assert rep["edges_dropped_unresolved"] == 1, "the edge to the non-existent file is not stored"
    mods = store.get_neighbours(commit_node_id(REPO, "4aa68d5"), relationship=R.MODIFIES)
    assert [n.node_id for _, n in mods] == [file_node_id(REPO, "src/flask/ctx.py")]
    resolved = store.get_neighbours(f"issue:{REPO}:123", relationship=R.RESOLVED_BY)
    assert [n.node_id for _, n in resolved] == [commit_node_id(REPO, "4aa68d5")]


def test_expansion_never_routes_through_the_repository_hub():
    store, _, _ = build()
    found = {c["node"].node_id for c in store.expand(file_node_id(REPO, "src/flask/json.py"), max_depth=3)}
    # json.py is only connected to the others via the Repository node: nothing may be reached
    assert not any(n.startswith("file:") for n in found)
    near_app = {c["node"].node_id: c for c in store.expand(file_node_id(REPO, "src/flask/app.py"), max_depth=2)}
    assert file_node_id(REPO, "src/flask/ctx.py") in near_app
    assert near_app[file_node_id(REPO, "src/flask/ctx.py")]["path"][0][0] == R.IMPORTS


def test_co_changed_ranks_by_shared_commits_and_edges_to_missing_nodes_are_not_invented():
    store = InMemoryGraphStore()
    for p in ("a.py", "b.py", "c.py"):
        store.upsert_node(GraphNode(file_node_id("o/r", p), NodeLabel.FILE, {"file_path": p}))
    # c.py changes with a.py twice but also in 6 other commits (like a changelog): b.py ranks first
    history = [["a.py", "b.py"], ["a.py", "b.py"], ["a.py", "c.py"], ["a.py", "c.py"]] + [["c.py"]] * 6
    for i, touched in enumerate(history):
        cid = commit_node_id("o/r", f"s{i}")
        store.upsert_node(GraphNode(cid, NodeLabel.COMMIT))
        for p in touched:
            store.upsert_edge(GraphEdge(cid, file_node_id("o/r", p), R.MODIFIES))
    ranked = [(n.properties["file_path"], k) for n, k in store.co_changed(file_node_id("o/r", "a.py"))]
    assert ranked == [("b.py", 2), ("c.py", 2)]
    assert store.co_changed(file_node_id("o/r", "a.py"), min_shared=3) == []
    store.upsert_edge(GraphEdge(file_node_id("o/r", "a.py"), "file:o/r:missing.py", R.IMPORTS))
    assert store.get_node("file:o/r:missing.py") is None
