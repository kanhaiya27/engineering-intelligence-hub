"""
Tests for EngineeringGraphBuilder and Knowledge Graph Query Utilities
"""

import pytest

from knowledge.graph.base import NodeLabel, RelationshipType
from knowledge.graph.builder import EngineeringGraphBuilder
from knowledge.graph.in_memory import InMemoryGraphStore
from knowledge.graph.queries import (
    find_dependencies,
    find_issue_commits,
    find_modified_files,
    find_related_files,
    get_entity,
    get_neighborhood,
    get_subgraph,
)
from knowledge.schemas.artifacts import (
    ArchitectureDecision,
    ArtifactType,
    Commit,
    Issue,
    PullRequest,
    SourceFile,
)


@pytest.fixture
def graph_setup():
    store = InMemoryGraphStore()
    store.connect()
    builder = EngineeringGraphBuilder(graph_store=store)

    code = """
import sys
class RouteHandler:
    def handle_request(self):
        return 'ok'
"""
    src = SourceFile(
        artifact_id="art-src-1",
        artifact_type=ArtifactType.SOURCE_CODE,
        repository="pallets/flask",
        commit_sha="4aa68d5",
        source_path="src/flask/app.py",
        raw_content=code,
        language="python",
    )

    commit = Commit(
        artifact_id="art-commit-1",
        artifact_type=ArtifactType.COMMIT,
        repository="pallets/flask",
        sha="4aa68d5",
        author_name="Armin Ronacher",
        message="feat: improve routing",
        committed_at="2024-01-01T00:00:00Z",
        files_changed=["src/flask/app.py"],
        insertions=10,
        deletions=2,
    )

    issue = Issue(
        artifact_id="art-issue-1",
        artifact_type=ArtifactType.ISSUE,
        repository="pallets/flask",
        issue_number=123,
        title="Routing bug with custom prefix",
        author="user1",
        resolved_by_commit="4aa68d5",
        linked_pull_requests=["456"],
    )

    pr = PullRequest(
        artifact_id="art-pr-1",
        artifact_type=ArtifactType.PULL_REQUEST,
        repository="pallets/flask",
        pr_number=456,
        title="Fix routing bug",
        author="user2",
        merge_commit_sha="4aa68d5",
        files_changed=["src/flask/app.py"],
    )

    adr = ArchitectureDecision(
        artifact_id="art-adr-1",
        artifact_type=ArtifactType.ARCHITECTURE_DECISION,
        repository="pallets/flask",
        decision_id="ADR-001",
        title="Use Scaffold base class",
        status="accepted",
        source_path="src/flask/app.py",
    )

    return {
        "store": store,
        "builder": builder,
        "artifacts": [src, commit, issue, pr, adr],
    }


def test_engineering_graph_builder_and_queries(graph_setup):
    store = graph_setup["store"]
    builder = graph_setup["builder"]
    artifacts = graph_setup["artifacts"]

    metrics = builder.build_repository_graph(
        repository="pallets/flask",
        artifacts=artifacts,
        commit_sha="4aa68d5",
    )

    assert metrics["status"] == "completed"
    assert metrics["total_nodes"] > 5
    assert metrics["total_edges"] > 5

    # 1. Query entity
    repo_node = get_entity(store, "repo:pallets/flask")
    assert repo_node is not None
    assert repo_node.label == NodeLabel.REPOSITORY

    # 2. Issue -> Commit query
    commits = find_issue_commits(store, "issue:pallets/flask:123")
    assert len(commits) == 1
    assert commits[0].node_id == "commit:pallets/flask:4aa68d5"

    # 3. Commit -> Modified Files query
    mod_files = find_modified_files(store, "commit:pallets/flask:4aa68d5")
    assert len(mod_files) == 1
    assert mod_files[0].properties["file_path"] == "src/flask/app.py"

    # 4. Subgraph extraction
    subgraph = get_subgraph(store, "issue:pallets/flask:123", max_depth=2)
    assert len(subgraph["nodes"]) >= 2
    assert len(subgraph["edges"]) >= 1
