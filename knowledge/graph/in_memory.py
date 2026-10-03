"""
Engineering Intelligence Hub — In-Memory Graph Store
=====================================================
Lightweight in-memory graph store implementing BaseGraphStore for fast,
deterministic unit testing without external database dependencies.
"""

from __future__ import annotations

from collections import deque
from typing import Any, Dict, List, Optional, Set, Tuple

from core.logging import get_logger
from knowledge.graph.base import BaseGraphStore, GraphEdge, GraphNode

logger = get_logger(__name__)


class InMemoryGraphStore(BaseGraphStore):
    """
    In-memory graph database implementation of BaseGraphStore.
    """

    def __init__(self) -> None:
        self._nodes: Dict[str, GraphNode] = {}
        # Adjacency: source_id -> list of GraphEdge
        self._out_edges: Dict[str, List[GraphEdge]] = {}
        # Adjacency: target_id -> list of GraphEdge
        self._in_edges: Dict[str, List[GraphEdge]] = {}
        self._connected: bool = False

    @property
    def store_name(self) -> str:
        return "in_memory_graph"

    def connect(self) -> None:
        self._connected = True
        logger.debug("InMemoryGraphStore connected.")

    def disconnect(self) -> None:
        self._connected = False
        logger.debug("InMemoryGraphStore disconnected.")

    def upsert_node(self, node: GraphNode) -> str:
        self._nodes[node.node_id] = node
        if node.node_id not in self._out_edges:
            self._out_edges[node.node_id] = []
        if node.node_id not in self._in_edges:
            self._in_edges[node.node_id] = []
        return node.node_id

    def upsert_edge(self, edge: GraphEdge) -> None:
        if edge.source_id not in self._nodes:
            # Auto-create source node placeholder if missing
            self.upsert_node(GraphNode(node_id=edge.source_id, label="Unknown"))
        if edge.target_id not in self._nodes:
            # Auto-create target node placeholder if missing
            self.upsert_node(GraphNode(node_id=edge.target_id, label="Unknown"))

        # Deduplicate existing edge with same source, target, and relationship
        self._out_edges[edge.source_id] = [
            e for e in self._out_edges.get(edge.source_id, [])
            if not (e.target_id == edge.target_id and e.relationship == edge.relationship)
        ]
        self._out_edges[edge.source_id].append(edge)

        self._in_edges[edge.target_id] = [
            e for e in self._in_edges.get(edge.target_id, [])
            if not (e.source_id == edge.source_id and e.relationship == edge.relationship)
        ]
        self._in_edges[edge.target_id].append(edge)

    def get_node(self, node_id: str, label: Optional[str] = None) -> Optional[GraphNode]:
        node = self._nodes.get(node_id)
        if node and label and node.label != label:
            return None
        return node

    def get_neighbours(
        self,
        node_id: str,
        relationship: Optional[str] = None,
        direction: str = "outbound",
        max_depth: int = 1,
    ) -> List[Tuple[GraphEdge, GraphNode]]:
        if node_id not in self._nodes:
            return []

        results: List[Tuple[GraphEdge, GraphNode]] = []
        visited_nodes: Set[str] = {node_id}
        queue: deque[Tuple[str, int]] = deque([(node_id, 0)])

        while queue:
            curr_id, curr_depth = queue.popleft()
            if curr_depth >= max_depth:
                continue

            edges_to_check: List[GraphEdge] = []
            if direction in {"outbound", "both"}:
                edges_to_check.extend(self._out_edges.get(curr_id, []))
            if direction in {"inbound", "both"}:
                edges_to_check.extend(self._in_edges.get(curr_id, []))

            for edge in edges_to_check:
                if relationship and edge.relationship != relationship:
                    continue

                neighbor_id = edge.target_id if edge.source_id == curr_id else edge.source_id
                neighbor_node = self._nodes.get(neighbor_id)
                if neighbor_node:
                    results.append((edge, neighbor_node))
                    if neighbor_id not in visited_nodes:
                        visited_nodes.add(neighbor_id)
                        queue.append((neighbor_id, curr_depth + 1))

        return results

    def query(self, query_string: str, parameters: Optional[Dict[str, Any]] = None) -> List[Dict]:
        """Simple in-memory entity filter simulation for basic query tests."""
        params = parameters or {}
        label = params.get("label")
        repo = params.get("repository")

        results = []
        for n in self._nodes.values():
            if label and n.label != label:
                continue
            if repo and n.properties.get("repository") != repo:
                continue
            results.append({"n": n.properties, "node_id": n.node_id, "label": n.label})
        return results

    def delete_node(self, node_id: str) -> bool:
        if node_id not in self._nodes:
            return False

        del self._nodes[node_id]

        # Clean out edges
        if node_id in self._out_edges:
            out_e = self._out_edges.pop(node_id)
            for e in out_e:
                if e.target_id in self._in_edges:
                    self._in_edges[e.target_id] = [ie for ie in self._in_edges[e.target_id] if ie.source_id != node_id]

        # Clean in edges
        if node_id in self._in_edges:
            in_e = self._in_edges.pop(node_id)
            for e in in_e:
                if e.source_id in self._out_edges:
                    self._out_edges[e.source_id] = [oe for oe in self._out_edges[e.source_id] if oe.target_id != node_id]

        return True

    def count_nodes(self, label: Optional[str] = None) -> int:
        if label:
            return sum(1 for n in self._nodes.values() if n.label == label)
        return len(self._nodes)

    def count_edges(self, relationship: Optional[str] = None) -> int:
        total = 0
        seen_edges = set()
        for edge_list in self._out_edges.values():
            for e in edge_list:
                key = (e.source_id, e.target_id, e.relationship)
                if key not in seen_edges:
                    seen_edges.add(key)
                    if relationship is None or e.relationship == relationship:
                        total += 1
        return total
