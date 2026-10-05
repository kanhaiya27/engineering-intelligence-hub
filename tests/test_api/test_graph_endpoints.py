"""
Tests for Knowledge Graph REST API Endpoints
"""

import pytest
from fastapi.testclient import TestClient

from apps.api.main import app
from apps.api.routers import graph as graph_router
from apps.api.routers.graph import get_graph_store
from knowledge.graph.base import GraphEdge, GraphNode, NodeLabel, RelationshipType
from knowledge.graph.in_memory import InMemoryGraphStore

client = TestClient(app)


@pytest.fixture(autouse=True)
def isolated_graph_store(monkeypatch):
    """Never write test fixtures into the real Neo4j graph (it now connects via .env)."""
    store = InMemoryGraphStore()
    store.connect()
    monkeypatch.setattr(graph_router, "_graph_store", store)
    return store


def test_graph_api_health():
    res = client.get("/graph/health")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "available"
    assert "node_count" in data
    assert "edge_count" in data


def test_graph_api_entity_and_neighbors():
    store = get_graph_store()
    node_a = GraphNode("test:node:a", NodeLabel.FILE, {"name": "a.py"})
    node_b = GraphNode("test:node:b", NodeLabel.MODULE, {"name": "a"})
    store.upsert_node(node_a)
    store.upsert_node(node_b)
    store.upsert_edge(GraphEdge("test:node:a", "test:node:b", RelationshipType.CONTAINS))

    # Get Entity
    res_entity = client.get("/graph/entity/test:node:a")
    assert res_entity.status_code == 200
    data_entity = res_entity.json()
    assert data_entity["node_id"] == "test:node:a"
    assert data_entity["label"] == NodeLabel.FILE

    # Get Neighbors
    res_neigh = client.get("/graph/neighbors/test:node:a")
    assert res_neigh.status_code == 200
    data_neigh = res_neigh.json()
    assert data_neigh["neighbor_count"] >= 1
    assert data_neigh["neighbors"][0]["node_id"] == "test:node:b"
