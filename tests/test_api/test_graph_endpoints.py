"""
Tests for Knowledge Graph REST API Endpoints

The endpoints run against an in-memory store. These tests used to write fixture nodes
(test:node:a / test:node:b) into whatever store the API found, i.e. the LIVE Neo4j experiment
graph, which they changed for good (found 2026-10-05: 37,066 -> 37,068 nodes).
"""

import pytest
from fastapi.testclient import TestClient

from apps.api.main import app
from apps.api.routers import graph as graph_router
from knowledge.graph.base import GraphEdge, GraphNode, NodeLabel, RelationshipType
from knowledge.graph.in_memory import InMemoryGraphStore


@pytest.fixture
def store(monkeypatch):
    mem = InMemoryGraphStore()
    mem.connect()
    monkeypatch.setattr(graph_router, "_graph_store", mem)
    return mem


@pytest.fixture
def client(store):
    return TestClient(app)


def test_graph_api_health(client):
    res = client.get("/graph/health")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "available"
    assert "node_count" in data
    assert "edge_count" in data


def test_graph_api_entity_and_neighbors(client, store):
    store.upsert_node(GraphNode("test:node:a", NodeLabel.FILE, {"name": "a.py"}))
    store.upsert_node(GraphNode("test:node:b", NodeLabel.MODULE, {"name": "a"}))
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


def test_tests_never_touch_the_live_graph(store):
    assert graph_router.get_graph_store() is store
