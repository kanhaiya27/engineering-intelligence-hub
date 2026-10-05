"""
Engineering Intelligence Hub — Knowledge Graph Builder
======================================================
Persists the graph of each repository (extracted by `RepositoryGraphExtractor`) into a
graph store and reports counts that are READ BACK from the store, so a reported
number is what the store actually holds (the previous builder counted attempted
writes; Neo4j silently skips an edge whose endpoint is missing).
"""

from __future__ import annotations

import time
from collections import Counter
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from core.logging import get_logger
from knowledge.graph.base import BaseGraphStore, GraphEdge, GraphNode, NodeLabel, RelationshipType
from knowledge.graph.extractor import RepositoryGraphExtractor, commit_node_id, file_node_id, repo_node_id
from knowledge.schemas.artifacts import (
    ArchitectureDecision,
    BaseArtifact,
    Commit,
    IncidentReport,
    Issue,
    PullRequest,
)

logger = get_logger(__name__)


class EngineeringGraphBuilder:
    """Builds and persists the engineering knowledge graph, one repository at a time."""

    def __init__(self, graph_store: BaseGraphStore) -> None:
        self.graph_store = graph_store

    def build_repository_graph(
        self,
        repository: str,
        commit_sha: str,
        files: Iterable[Tuple[str, str]],
        repo_dir: Optional[Path] = None,
        max_commits: int = 500,
        max_files_per_commit: int = 30,
    ) -> Dict[str, Any]:
        """Extract + persist one repository's graph. `files` = (path, content) of every indexed file."""
        t0 = time.perf_counter()
        g = RepositoryGraphExtractor(repository, commit_sha).extract(
            files, repo_dir=repo_dir, max_commits=max_commits, max_files_per_commit=max_files_per_commit)
        t_extract = time.perf_counter() - t0
        self.graph_store.upsert_nodes(list(g.nodes.values()))
        self.graph_store.upsert_edges(list(g.edges.values()))
        report = {
            "repository": repository,
            "commit_sha": commit_sha,
            "nodes_written": len(g.nodes),
            "edges_written": len(g.edges),
            "nodes_by_label": dict(Counter(n.label for n in g.nodes.values()).most_common()),
            "edges_by_type": dict(Counter(e.relationship for e in g.edges.values()).most_common()),
            "edges_dropped_unresolved": g.dropped_edges,
            "python_parse_errors": len(g.parse_errors),
            "history": g.history,
            "files": sum(1 for n in g.nodes.values() if n.label == NodeLabel.FILE),
            "extract_seconds": round(t_extract, 2),
            "write_seconds": round(time.perf_counter() - t0 - t_extract, 2),
        }
        logger.info(f"Graph for {repository}: {report['nodes_written']} nodes, {report['edges_written']} edges")
        return report

    # ------------------------------------------------------------------
    # Engineering history artifacts (plan Tier 1: commits, PRs, issues, ADRs,
    # incidents). Same ids as the code graph, so e.g. an issue -> commit ->
    # file path reaches the File node the retriever seeds from.
    # ------------------------------------------------------------------
    def build_artifact_graph(self, artifact: BaseArtifact) -> Tuple[List[GraphNode], List[GraphEdge]]:
        """Nodes and edges for one history artifact (SourceFile is handled per repository)."""
        repo = artifact.repository
        rid = repo_node_id(repo)
        nodes: List[GraphNode] = []
        edges: List[GraphEdge] = []

        def node(nid: str, label: str, **props) -> None:
            nodes.append(GraphNode(nid, label, {"repository": repo, "artifact_id": artifact.artifact_id, **props}))
            edges.append(GraphEdge(rid, nid, RelationshipType.CONTAINS))

        if isinstance(artifact, Commit):
            sha = getattr(artifact, "sha", None) or getattr(artifact, "commit_sha", None) or "unknown"
            cid = commit_node_id(repo, sha)
            node(cid, NodeLabel.COMMIT, commit_sha=sha, name=(artifact.message or "")[:200],
                 author=getattr(artifact, "author_name", None), date=str(getattr(artifact, "committed_at", "") or ""),
                 lines_added=getattr(artifact, "insertions", None), lines_deleted=getattr(artifact, "deletions", None))
            for path in artifact.files_changed:
                edges.append(GraphEdge(cid, file_node_id(repo, path), RelationshipType.MODIFIES))
        elif isinstance(artifact, PullRequest):
            pid = f"pr:{repo}:{artifact.pr_number}"
            node(pid, NodeLabel.PULL_REQUEST, pr_number=artifact.pr_number, name=artifact.title,
                 author=artifact.author, merged_at=str(getattr(artifact, "merged_at", "") or ""))
            if getattr(artifact, "merge_commit_sha", None):
                edges.append(GraphEdge(pid, commit_node_id(repo, artifact.merge_commit_sha), RelationshipType.LINKED_TO))
            for path in artifact.files_changed:
                edges.append(GraphEdge(pid, file_node_id(repo, path), RelationshipType.MODIFIES))
        elif isinstance(artifact, Issue):
            iid = f"issue:{repo}:{artifact.issue_number}"
            node(iid, NodeLabel.ISSUE, issue_number=artifact.issue_number, name=artifact.title,
                 author=artifact.author, labels=list(artifact.labels or []))
            for pr in getattr(artifact, "linked_pull_requests", None) or []:
                edges.append(GraphEdge(iid, f"pr:{repo}:{pr}", RelationshipType.LINKED_TO))
            closed_by = getattr(artifact, "resolved_by_commit", None) or getattr(artifact, "closed_by_commit", None)
            if closed_by:
                edges.append(GraphEdge(iid, commit_node_id(repo, closed_by), RelationshipType.RESOLVED_BY))
        elif isinstance(artifact, ArchitectureDecision):
            did = getattr(artifact, "decision_id", None) or artifact.artifact_id
            aid = f"adr:{repo}:{did}"
            node(aid, NodeLabel.ARCHITECTURE_DECISION, decision_id=did, name=artifact.title, status=artifact.status)
            if artifact.source_path:
                edges.append(GraphEdge(aid, file_node_id(repo, artifact.source_path), RelationshipType.AFFECTED))
        elif isinstance(artifact, IncidentReport):
            inc = getattr(artifact, "incident_id", None) or artifact.artifact_id
            nid = f"incident:{repo}:{inc}"
            node(nid, NodeLabel.INCIDENT, incident_id=inc, name=artifact.title)
            for sha in artifact.linked_commits:
                edges.append(GraphEdge(nid, commit_node_id(repo, sha), RelationshipType.LINKED_TO))
        return nodes, edges

    def build_history_graph(self, artifacts: Iterable[BaseArtifact]) -> Dict[str, Any]:
        """Persist history artifacts; edges whose endpoint does not exist are not stored."""
        nodes: Dict[str, GraphNode] = {}
        edges: List[GraphEdge] = []
        for art in artifacts:
            n, e = self.build_artifact_graph(art)
            nodes.update({x.node_id: x for x in n})
            edges.extend(e)
        self.graph_store.upsert_nodes(list(nodes.values()))
        known = set(nodes)
        kept = [e for e in edges if (e.source_id in known or self.graph_store.get_node(e.source_id))
                and (e.target_id in known or self.graph_store.get_node(e.target_id))]
        self.graph_store.upsert_edges(kept)
        return {"nodes_written": len(nodes), "edges_written": len(kept), "edges_dropped_unresolved": len(edges) - len(kept)}
