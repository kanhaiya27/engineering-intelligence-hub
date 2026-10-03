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
