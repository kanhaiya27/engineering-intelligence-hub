"""
Engineering Intelligence Hub — Engineering Knowledge Graph Builder
===================================================================
Builds a provenance-preserving knowledge graph from repository artifacts,
connecting source code structures, Git commits, issues, PRs, and tests.
"""

from __future__ import annotations

import time
from typing import Any, Dict, List, Optional, Tuple

from core.logging import get_logger
from knowledge.graph.base import (
    BaseGraphStore,
    GraphEdge,
    GraphNode,
    NodeLabel,
    RelationshipType,
)
from knowledge.graph.extractor import ASTGraphExtractor
from knowledge.schemas.artifacts import (
    ArchitectureDecision,
    BaseArtifact,
    Commit,
    IncidentReport,
    Issue,
    PullRequest,
    SourceFile,
)

logger = get_logger(__name__)


class EngineeringGraphBuilder:
    """
    Constructs and persists engineering knowledge graph entities and relationships.
    """

    def __init__(
        self,
        graph_store: BaseGraphStore,
        ast_extractor: Optional[ASTGraphExtractor] = None,
    ) -> None:
        self.graph_store = graph_store
        self.ast_extractor = ast_extractor or ASTGraphExtractor()

    def build_artifact_graph(
        self,
        artifact: BaseArtifact,
        repository_url: Optional[str] = None,
    ) -> Tuple[List[GraphNode], List[GraphEdge]]:
        """
        Extract graph nodes and edges from a single artifact.
        """
        nodes: List[GraphNode] = []
        edges: List[GraphEdge] = []

        repo = artifact.repository
        commit = getattr(artifact, "commit_sha", None) or "latest"
        repo_node_id = f"repo:{repo}"

        # 1. SourceFile Artifact
        if isinstance(artifact, SourceFile):
            file_nodes, file_edges = self.ast_extractor.extract(artifact)
            nodes.extend(file_nodes)
            edges.extend(file_edges)

            # Link repo -> file
            if file_nodes:
                file_node = file_nodes[0]
                edges.append(GraphEdge(
                    source_id=repo_node_id,
                    target_id=file_node.node_id,
                    relationship=RelationshipType.CONTAINS,
                ))

        # 2. Commit Artifact
        elif isinstance(artifact, Commit):
            commit_sha = getattr(artifact, "sha", None) or getattr(artifact, "commit_sha", "unknown")
            commit_node_id = f"commit:{repo}:{commit_sha}"
            commit_node = GraphNode(
                node_id=commit_node_id,
                label=NodeLabel.COMMIT,
                properties={
                    "repository": repo,
                    "commit_sha": commit_sha,
                    "author": getattr(artifact, "author_name", None) or getattr(artifact, "author", "unknown"),
                    "message": artifact.message,
                    "committed_at": getattr(artifact, "committed_at", None),
                    "lines_added": getattr(artifact, "insertions", None) or getattr(artifact, "lines_added", 0),
                    "lines_deleted": getattr(artifact, "deletions", None) or getattr(artifact, "lines_deleted", 0),
                    "artifact_id": artifact.artifact_id,
                },
            )
            nodes.append(commit_node)
            edges.append(GraphEdge(
                source_id=repo_node_id,
                target_id=commit_node_id,
                relationship=RelationshipType.CONTAINS,
            ))

            # Link commit -> modified files
            for path in artifact.files_changed:
                target_file_id = f"file:{repo}:{commit_sha}:{path}"
                edges.append(GraphEdge(
                    source_id=commit_node_id,
                    target_id=target_file_id,
                    relationship=RelationshipType.MODIFIES,
                    properties={"file_path": path},
                ))

        # 3. Pull Request Artifact
        elif isinstance(artifact, PullRequest):
            pr_node_id = f"pr:{repo}:{artifact.pr_number}"
            pr_node = GraphNode(
                node_id=pr_node_id,
                label=NodeLabel.PULL_REQUEST,
                properties={
                    "repository": repo,
                    "pr_number": artifact.pr_number,
                    "title": artifact.title,
                    "author": artifact.author,
                    "merged_at": getattr(artifact, "merged_at", None),
                    "merge_commit_sha": getattr(artifact, "merge_commit_sha", None),
                    "artifact_id": artifact.artifact_id,
                },
            )
            nodes.append(pr_node)
            edges.append(GraphEdge(
                source_id=repo_node_id,
                target_id=pr_node_id,
                relationship=RelationshipType.CONTAINS,
            ))

            # Link PR -> merge commit if present
            if getattr(artifact, "merge_commit_sha", None):
                commit_id = f"commit:{repo}:{artifact.merge_commit_sha}"
                edges.append(GraphEdge(
                    source_id=pr_node_id,
                    target_id=commit_id,
                    relationship=RelationshipType.LINKED_TO,
                ))

            # Link PR -> modified files
            for path in artifact.files_changed:
                target_file_id = f"file:{repo}:{commit}:{path}"
                edges.append(GraphEdge(
                    source_id=pr_node_id,
                    target_id=target_file_id,
                    relationship=RelationshipType.MODIFIES,
                    properties={"file_path": path},
                ))

        # 4. Issue Artifact
        elif isinstance(artifact, Issue):
            issue_node_id = f"issue:{repo}:{artifact.issue_number}"
            issue_node = GraphNode(
                node_id=issue_node_id,
                label=NodeLabel.ISSUE,
                properties={
                    "repository": repo,
                    "issue_number": artifact.issue_number,
                    "title": artifact.title,
                    "author": artifact.author,
                    "labels": artifact.labels,
                    "artifact_id": artifact.artifact_id,
                },
            )
            nodes.append(issue_node)
            edges.append(GraphEdge(
                source_id=repo_node_id,
                target_id=issue_node_id,
                relationship=RelationshipType.CONTAINS,
            ))

            # Link Issue -> Linked PRs
            linked_prs = getattr(artifact, "linked_pull_requests", None) or getattr(artifact, "linked_pr_numbers", [])
            for pr_ref in linked_prs:
                target_pr_id = f"pr:{repo}:{pr_ref}"
                edges.append(GraphEdge(
                    source_id=issue_node_id,
                    target_id=target_pr_id,
                    relationship=RelationshipType.LINKED_TO,
                ))

            # Link Issue -> Closed by commit if present
            closed_by = getattr(artifact, "resolved_by_commit", None) or getattr(artifact, "closed_by_commit", None)
            if closed_by:
                commit_id = f"commit:{repo}:{closed_by}"
                edges.append(GraphEdge(
                    source_id=issue_node_id,
                    target_id=commit_id,
                    relationship=RelationshipType.RESOLVED_BY,
                ))

        # 5. Architecture Decision Record (ADR)
        elif isinstance(artifact, ArchitectureDecision):
            decision_id = getattr(artifact, "decision_id", None) or getattr(artifact, "adr_id", artifact.artifact_id)
            adr_node_id = f"adr:{repo}:{decision_id}"
            adr_node = GraphNode(
                node_id=adr_node_id,
                label=NodeLabel.ARCHITECTURE_DECISION,
                properties={
                    "repository": repo,
                    "decision_id": decision_id,
                    "title": artifact.title,
                    "status": artifact.status,
                    "artifact_id": artifact.artifact_id,
                },
            )
            nodes.append(adr_node)
            edges.append(GraphEdge(
                source_id=repo_node_id,
                target_id=adr_node_id,
                relationship=RelationshipType.CONTAINS,
            ))

            if artifact.source_path:
                file_id = f"file:{repo}:{commit}:{artifact.source_path}"
                edges.append(GraphEdge(
                    source_id=adr_node_id,
                    target_id=file_id,
                    relationship=RelationshipType.AFFECTED,
                ))

        # 6. Incident Report
        elif isinstance(artifact, IncidentReport):
            incident_id = getattr(artifact, "incident_id", None) or artifact.artifact_id
            inc_node_id = f"incident:{repo}:{incident_id}"
            inc_node = GraphNode(
                node_id=inc_node_id,
                label=NodeLabel.INCIDENT,
                properties={
                    "repository": repo,
                    "incident_id": incident_id,
                    "title": artifact.title,
                    "artifact_id": artifact.artifact_id,
                },
            )
            nodes.append(inc_node)
            edges.append(GraphEdge(
                source_id=repo_node_id,
                target_id=inc_node_id,
                relationship=RelationshipType.CONTAINS,
            ))

            for c_sha in artifact.linked_commits:
                commit_id = f"commit:{repo}:{c_sha}"
                edges.append(GraphEdge(
                    source_id=inc_node_id,
                    target_id=commit_id,
                    relationship=RelationshipType.LINKED_TO,
                ))

        return nodes, edges

    def build_repository_graph(
        self,
        repository: str,
        artifacts: List[BaseArtifact],
        commit_sha: Optional[str] = None,
        repository_url: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Build and persist knowledge graph for a complete repository and its artifacts.
        """
        start_time = time.perf_counter()

        # 1. Create Root Repository Node
        repo_node_id = f"repo:{repository}"
        repo_node = GraphNode(
            node_id=repo_node_id,
            label=NodeLabel.REPOSITORY,
            properties={
                "repository": repository,
                "commit_sha": commit_sha or "latest",
                "url": repository_url,
            },
        )
        self.graph_store.upsert_node(repo_node)

        total_nodes = 1
        total_edges = 0
        failed_count = 0

        # 2. Process all artifacts
        for art in artifacts:
            try:
                nodes, edges = self.build_artifact_graph(art, repository_url=repository_url)
                for n in nodes:
                    self.graph_store.upsert_node(n)
                    total_nodes += 1
                for e in edges:
                    self.graph_store.upsert_edge(e)
                    total_edges += 1
            except Exception as e:
                failed_count += 1
                logger.warning(f"Failed to extract graph from artifact {art.artifact_id}: {e}")

        duration_ms = (time.perf_counter() - start_time) * 1000.0

        metrics = {
            "repository": repository,
            "commit_sha": commit_sha or "latest",
            "total_nodes": total_nodes,
            "total_edges": total_edges,
            "failed_artifacts": failed_count,
            "duration_ms": round(duration_ms, 2),
            "status": "completed",
        }

        logger.info(
            f"Knowledge Graph built for '{repository}': {total_nodes} nodes, "
            f"{total_edges} edges in {duration_ms:.2f}ms"
        )
        return metrics
