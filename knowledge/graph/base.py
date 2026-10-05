"""
Engineering Intelligence Hub — Abstract Graph Store Interface
=============================================================
Defines the contract for all graph database backends (Neo4j, etc.).

The graph represents engineering knowledge relationships:
    Repository → contains → Component
    Component → implemented_by → File
    File → modified_by → Commit
    Issue → resolved_by → Commit
    Incident → affected → Service
    Test → validates → Function

Phase-0: Interface only. Neo4j driver is NOT imported here.
Phase-1: Implement Neo4jGraphStore in knowledge/graph/neo4j_store.py.

Node and edge labels use the vocabulary from the system specification.
Properties are passed as plain dicts (provider-agnostic).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Tuple


# ---------------------------------------------------------------------------
# Graph entity types — defined as strings to avoid tight coupling
# ---------------------------------------------------------------------------

class NodeLabel:
    """Canonical node label strings for the EIH knowledge graph."""
    REPOSITORY = "Repository"
    SERVICE = "Service"
    COMPONENT = "Component"
    FILE = "File"
    MODULE = "Module"
    CLASS = "Class"
    FUNCTION = "Function"
    METHOD = "Method"
    API = "API"
    DATABASE = "Database"
    ISSUE = "Issue"
    INCIDENT = "Incident"
    COMMIT = "Commit"
    PULL_REQUEST = "PullRequest"
    TEST = "Test"
    ARCHITECTURE_DECISION = "ArchitectureDecision"


class RelationshipType:
    """Canonical relationship type strings for the EIH knowledge graph."""
    CONTAINS = "CONTAINS"
    DEPENDS_ON = "DEPENDS_ON"
    IMPLEMENTED_BY = "IMPLEMENTED_BY"
    MODIFIED_BY = "MODIFIED_BY"
    MODIFIES = "MODIFIES"
    RESOLVED_BY = "RESOLVED_BY"
    RESOLVES = "RESOLVES"
    AFFECTED = "AFFECTED"
    VALIDATES = "VALIDATES"
    TESTED_BY = "TESTED_BY"
    TESTS = "TESTS"
    CALLS = "CALLS"
    CALLED_BY = "CALLED_BY"
    IMPORTS = "IMPORTS"
    IMPORTED_BY = "IMPORTED_BY"
    LINKED_TO = "LINKED_TO"
    SUPERSEDES = "SUPERSEDES"
    AUTHORED_BY = "AUTHORED_BY"


# ---------------------------------------------------------------------------
# Simple graph entity models (not Pydantic — intentionally lightweight)
# ---------------------------------------------------------------------------

class GraphNode:
    """A node in the engineering knowledge graph."""

    def __init__(
        self,
        node_id: str,
        label: str,
        properties: Optional[Dict[str, Any]] = None,
    ) -> None:
        self.node_id = node_id
        self.label = label
        self.properties: Dict[str, Any] = properties or {}

    def __repr__(self) -> str:  # pragma: no cover
        return f"GraphNode(id={self.node_id!r}, label={self.label!r})"


class GraphEdge:
    """A directed edge (relationship) in the engineering knowledge graph."""

    def __init__(
        self,
        source_id: str,
        target_id: str,
        relationship: str,
        properties: Optional[Dict[str, Any]] = None,
    ) -> None:
        self.source_id = source_id
        self.target_id = target_id
        self.relationship = relationship
        self.properties: Dict[str, Any] = properties or {}

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"GraphEdge({self.source_id!r} --[{self.relationship}]--> {self.target_id!r})"
        )


# ---------------------------------------------------------------------------
# Abstract graph store
# ---------------------------------------------------------------------------

class BaseGraphStore(ABC):
    """
    Abstract interface for the EIH engineering knowledge graph.

    All methods use plain Python types (str, dict, list) for provider
    independence. Concrete implementations translate these to Cypher,
    Gremlin, or SPARQL as appropriate.
    """

    @property
    @abstractmethod
    def store_name(self) -> str:
        """Human-readable name of the graph backend."""
        ...

    @abstractmethod
    def connect(self) -> None:
        """Establish a connection to the graph database."""
        ...

    @abstractmethod
    def disconnect(self) -> None:
        """Close the connection."""
        ...

    @abstractmethod
    def upsert_node(self, node: GraphNode) -> str:
        """
        Insert or update a node by node_id + label.

        Returns
        -------
        str
            Internal graph ID of the upserted node.
        """
        ...

    @abstractmethod
    def upsert_edge(self, edge: GraphEdge) -> None:
        """
        Create or update a directed relationship between two nodes.
        Both source and target nodes must exist before calling this.
        """
        ...

    @abstractmethod
    def get_node(self, node_id: str, label: Optional[str] = None) -> Optional[GraphNode]:
        """
        Retrieve a node by its ID and optional label.
        Returns None if not found.
        """
        ...

    @abstractmethod
    def get_neighbours(
        self,
        node_id: str,
        relationship: Optional[str] = None,
        direction: str = "outbound",
        max_depth: int = 1,
    ) -> List[Tuple[GraphEdge, GraphNode]]:
        """
        Return (edge, node) pairs reachable from node_id.

        Parameters
        ----------
        node_id : str
        relationship : str, optional
            Filter by relationship type.
        direction : str
            'outbound' | 'inbound' | 'both'
        max_depth : int
            Graph traversal depth (default 1 = immediate neighbours).
        """
        ...

    @abstractmethod
    def query(self, query_string: str, parameters: Optional[Dict[str, Any]] = None) -> List[Dict]:
        """
        Execute a raw graph query (Cypher, Gremlin, etc.).

        This is the escape hatch for complex traversals not covered
        by the higher-level interface methods.

        Parameters
        ----------
        query_string : str
            Provider-specific query language string.
        parameters : dict, optional
            Named parameters for the query.

        Returns
        -------
        List[Dict]
            List of result records as plain dicts.
        """
        ...

    @abstractmethod
    def delete_node(self, node_id: str) -> bool:
        """
        Delete a node and all its relationships.

        Returns
        -------
        bool
            True if the node existed and was deleted.
        """
        ...

    @abstractmethod
    def count_nodes(self, label: Optional[str] = None) -> int:
        """
        Return the total number of nodes, optionally filtered by label.
        """
        ...

    @abstractmethod
    def count_edges(self, relationship: Optional[str] = None) -> int:
        """
        Return the total number of edges, optionally filtered by type.
        """
        ...

    # ------------------------------------------------------------------
    # Concrete helpers shared by all stores (Neo4j overrides them for speed)
    # ------------------------------------------------------------------

    def upsert_nodes(self, nodes: List[GraphNode]) -> None:
        for n in nodes:
            self.upsert_node(n)

    def upsert_edges(self, edges: List[GraphEdge]) -> None:
        for e in edges:
            self.upsert_edge(e)

    def expand(
        self,
        node_id: str,
        max_depth: int = 2,
        limit: int = 50,
        hub_labels: Tuple[str, ...] = ("Repository", "Commit"),
    ) -> List[Dict[str, Any]]:
        """Structural neighbours of a node, nearest first, never routed THROUGH a hub.

        Every file hangs off its Repository node and a commit links all files it
        touched, so walking through those hubs reaches arbitrary files at depth 2.
        Hubs are neither returned nor crossed (co-change is `co_changed`).
        Returns [{"node": GraphNode, "hop": int, "paths": [[(relationship, src_id, tgt_id), ...], ...],
                  "path": paths[0]}] — `paths` holds every shortest connection (up to 5).
        """
        seen = {node_id}
        frontier: List[Tuple[str, List[Tuple[str, str, str]]]] = [(node_id, [])]
        out: List[Dict[str, Any]] = []
        for hop in range(1, max_depth + 1):
            level: Dict[str, Dict[str, Any]] = {}
            for nid, path in frontier:
                for edge, nb in self.get_neighbours(nid, direction="both", max_depth=1):
                    if nb.node_id in seen or nb.label in hub_labels:
                        continue
                    entry = level.setdefault(nb.node_id, {"node": nb, "hop": hop, "paths": []})
                    if len(entry["paths"]) < 5:  # all shortest connections (e.g. IMPORTS and TESTS)
                        entry["paths"].append(path + [(edge.relationship, edge.source_id, edge.target_id)])
            for nid, entry in sorted(level.items()):
                seen.add(nid)
                entry["path"] = entry["paths"][0]
                out.append(entry)
                if len(out) >= limit:
                    return out
            frontier = [(nid, e["paths"][0]) for nid, e in sorted(level.items())]
        return out

    def co_changed(self, file_node_id: str, limit: int = 5, min_shared: int = 2) -> List[Tuple[GraphNode, int]]:
        """Files most strongly changed together with this one (Commit-MODIFIES->File).

        Ranked by cosine = shared / sqrt(changes(a) * changes(b)), so a file that changes
        with everything (e.g. a changelog) does not dominate; at least `min_shared`
        shared commits. Returns (node, shared commit count).
        """
        def n_changes(nid: str) -> int:
            return len(self.get_neighbours(nid, relationship=RelationshipType.MODIFIES, direction="inbound"))

        counts: Dict[str, int] = {}
        nodes: Dict[str, GraphNode] = {}
        for _, commit in self.get_neighbours(file_node_id, relationship=RelationshipType.MODIFIES,
                                             direction="inbound"):
            for _, other in self.get_neighbours(commit.node_id, relationship=RelationshipType.MODIFIES,
                                                direction="outbound"):
                if other.node_id != file_node_id:
                    counts[other.node_id] = counts.get(other.node_id, 0) + 1
                    nodes[other.node_id] = other
        mine = max(1, n_changes(file_node_id))
        scored = [(k, n, n / (mine * max(1, n_changes(k))) ** 0.5) for k, n in counts.items() if n >= min_shared]
        ranked = sorted(scored, key=lambda t: (-t[2], -t[1], t[0]))[:limit]
        return [(nodes[k], n) for k, n, _ in ranked]

    def clear(self) -> None:
        """Delete every node and edge (used before a full rebuild)."""
        raise NotImplementedError
