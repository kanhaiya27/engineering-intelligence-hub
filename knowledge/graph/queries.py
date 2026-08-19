"""
Engineering Intelligence Hub — Knowledge Graph Query Utilities
===============================================================
Convenience functions for structural traversals, neighborhood exploration,
and dependency queries on top of BaseGraphStore.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Set

from core.logging import get_logger
from knowledge.graph.base import BaseGraphStore, GraphEdge, GraphNode, NodeLabel, RelationshipType

logger = get_logger(__name__)


def get_entity(graph_store: BaseGraphStore, node_id: str) -> Optional[GraphNode]:
    """Retrieve an entity node by its node_id."""
    return graph_store.get_node(node_id)


def get_neighborhood(
    graph_store: BaseGraphStore,
    node_id: str,
    relationship: Optional[str] = None,
    direction: str = "both",
    max_depth: int = 1,
) -> List[Dict[str, Any]]:
    """
    Retrieve immediate neighbors and connecting relationships.
    """
    pairs = graph_store.get_neighbours(
        node_id=node_id,
        relationship=relationship,
        direction=direction,
        max_depth=max_depth,
    )
    results: List[Dict[str, Any]] = []
    for edge, node in pairs:
        results.append({
            "node_id": node.node_id,
            "label": node.label,
            "properties": node.properties,
            "relationship": edge.relationship,
            "relationship_properties": edge.properties,
            "source_id": edge.source_id,
            "target_id": edge.target_id,
        })
    return results


def find_dependencies(
    graph_store: BaseGraphStore,
    module_or_file_id: str,
) -> List[GraphNode]:
    """
    Find modules or components that this module depends on.
    """
    pairs = graph_store.get_neighbours(
        node_id=module_or_file_id,
        relationship=RelationshipType.DEPENDS_ON,
        direction="outbound",
        max_depth=1,
    )
    return [node for _, node in pairs]


def find_related_files(
    graph_store: BaseGraphStore,
    file_id: str,
) -> List[GraphNode]:
    """
    Find files connected through common imports, commits, PRs, or ADRs.
    """
    pairs = graph_store.get_neighbours(
        node_id=file_id,
        direction="both",
        max_depth=2,
    )
    related_files: List[GraphNode] = []
    seen = {file_id}
    for _, node in pairs:
        if node.label == NodeLabel.FILE and node.node_id not in seen:
            seen.add(node.node_id)
            related_files.append(node)
    return related_files


def find_issue_commits(
    graph_store: BaseGraphStore,
    issue_id: str,
) -> List[GraphNode]:
    """
    Find commits that resolved or are linked to an issue.
    """
    pairs = graph_store.get_neighbours(
        node_id=issue_id,
        relationship=RelationshipType.RESOLVED_BY,
        direction="outbound",
        max_depth=1,
    )
    return [node for _, node in pairs if node.label == NodeLabel.COMMIT]


def find_modified_files(
    graph_store: BaseGraphStore,
    commit_or_pr_id: str,
) -> List[GraphNode]:
    """
    Find files modified by a commit or pull request.
    """
    pairs = graph_store.get_neighbours(
        node_id=commit_or_pr_id,
        relationship=RelationshipType.MODIFIES,
        direction="outbound",
        max_depth=1,
    )
    return [node for _, node in pairs]


def get_subgraph(
    graph_store: BaseGraphStore,
    root_id: str,
    max_depth: int = 2,
) -> Dict[str, Any]:
    """
    Extract a connected subgraph starting from a root node.
    """
    root = graph_store.get_node(root_id)
    if not root:
        return {"nodes": [], "edges": [], "root_id": root_id}

    nodes: Dict[str, GraphNode] = {root.node_id: root}
    edges: List[GraphEdge] = []
    seen_edges: Set[Tuple[str, str, str]] = set()

    pairs = graph_store.get_neighbours(
        node_id=root_id,
        direction="both",
        max_depth=max_depth,
    )

    for edge, node in pairs:
        nodes[node.node_id] = node
        edge_key = (edge.source_id, edge.target_id, edge.relationship)
        if edge_key not in seen_edges:
            seen_edges.add(edge_key)
            edges.append(edge)

    return {
        "root_id": root_id,
        "nodes": [
            {"node_id": n.node_id, "label": n.label, "properties": n.properties}
            for n in nodes.values()
        ],
        "edges": [
            {
                "source_id": e.source_id,
                "target_id": e.target_id,
                "relationship": e.relationship,
                "properties": e.properties,
            }
            for e in edges
        ],
    }
