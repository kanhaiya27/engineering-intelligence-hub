"""
FastAPI Router for Engineering Knowledge Graph
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException, status

from core.logging import get_logger
from knowledge.graph.base import BaseGraphStore
from knowledge.graph.in_memory import InMemoryGraphStore
from knowledge.graph.neo4j import Neo4jGraphStore
from knowledge.graph.queries import get_entity, get_neighborhood

logger = get_logger(__name__)

router = APIRouter(prefix="/graph", tags=["Knowledge Graph"])

_graph_store: Optional[BaseGraphStore] = None


def get_graph_store() -> BaseGraphStore:
    global _graph_store
    if _graph_store is None:
        # Try Neo4j first, fallback to InMemoryGraphStore
        neo = Neo4jGraphStore()
        if neo.is_available():
            _graph_store = neo
        else:
            # Not silent: an empty in-memory graph looks "available" to callers.
            logger.warning(
                f"Neo4j not reachable at {neo.uri}; graph API is serving an EMPTY "
                "in-memory graph (check docker compose and EIH_GRAPH_* in .env)."
            )
            in_mem = InMemoryGraphStore()
            in_mem.connect()
            _graph_store = in_mem
    return _graph_store


@router.get("/health")
async def graph_health():
    store = get_graph_store()
    return {
        "status": "available",
        "store_name": store.store_name,
        "node_count": store.count_nodes(),
        "edge_count": store.count_edges(),
    }


@router.get("/entity/{node_id:path}")
async def get_graph_entity(node_id: str):
    store = get_graph_store()
    node = get_entity(store, node_id)
    if not node:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Entity '{node_id}' not found in knowledge graph.",
        )
    return {
        "node_id": node.node_id,
        "label": node.label,
        "properties": node.properties,
    }


@router.get("/neighbors/{node_id:path}")
async def get_graph_neighbors(
    node_id: str,
    relationship: Optional[str] = None,
    direction: str = "both",
    max_depth: int = 1,
):
    store = get_graph_store()
    node = get_entity(store, node_id)
    if not node:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Entity '{node_id}' not found in knowledge graph.",
        )

    neighbors = get_neighborhood(
        store,
        node_id=node_id,
        relationship=relationship,
        direction=direction,
        max_depth=max_depth,
    )
    return {
        "node_id": node_id,
        "neighbor_count": len(neighbors),
        "neighbors": neighbors,
    }
