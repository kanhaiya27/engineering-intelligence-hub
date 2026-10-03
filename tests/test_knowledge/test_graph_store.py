"""
Tests for GraphStore implementations (InMemoryGraphStore and Neo4j interface)
"""

import pytest

from knowledge.graph.base import GraphEdge, GraphNode, NodeLabel, RelationshipType
from knowledge.graph.in_memory import InMemoryGraphStore


@pytest.fixture
def in_memory_store():
    store = InMemoryGraphStore()
    store.connect()
    yield store
    store.disconnect()


def test_in_memory_node_crud(in_memory_store):
    store = in_memory_store
    node = GraphNode(
        node_id="file:flask:3.0.3:src/flask/app.py",
        label=NodeLabel.FILE,
        properties={"repository": "pallets/flask", "lines": 1500},
    )

    upserted_id = store.upsert_node(node)
    assert upserted_id == "file:flask:3.0.3:src/flask/app.py"
    assert store.count_nodes() == 1
    assert store.count_nodes(NodeLabel.FILE) == 1
    assert store.count_nodes(NodeLabel.CLASS) == 0

    fetched = store.get_node("file:flask:3.0.3:src/flask/app.py")
    assert fetched is not None
    assert fetched.properties["repository"] == "pallets/flask"

    # Delete
    deleted = store.delete_node("file:flask:3.0.3:src/flask/app.py")
    assert deleted is True
    assert store.count_nodes() == 0


def test_in_memory_edges_and_neighborhood(in_memory_store):
    store = in_memory_store

    # Nodes
    repo_node = GraphNode("repo:flask", NodeLabel.REPOSITORY, {"name": "flask"})
    file_node = GraphNode("file:app.py", NodeLabel.FILE, {"path": "app.py"})
    class_node = GraphNode("class:Flask", NodeLabel.CLASS, {"name": "Flask"})

    store.upsert_node(repo_node)
    store.upsert_node(file_node)
    store.upsert_node(class_node)

    # Edges
    store.upsert_edge(GraphEdge("repo:flask", "file:app.py", RelationshipType.CONTAINS))
    store.upsert_edge(GraphEdge("file:app.py", "class:Flask", RelationshipType.CONTAINS))

    assert store.count_edges() == 2
    assert store.count_edges(RelationshipType.CONTAINS) == 2

    # Outbound neighbors of repo:flask (depth 1)
    neighbors_d1 = store.get_neighbours("repo:flask", direction="outbound", max_depth=1)
    assert len(neighbors_d1) == 1
    assert neighbors_d1[0][1].node_id == "file:app.py"

    # Outbound neighbors of repo:flask (depth 2)
    neighbors_d2 = store.get_neighbours("repo:flask", direction="outbound", max_depth=2)
    neighbor_ids = {n.node_id for _, n in neighbors_d2}
    assert "file:app.py" in neighbor_ids
    assert "class:Flask" in neighbor_ids

    # Inbound neighbors of class:Flask
    inbound = store.get_neighbours("class:Flask", direction="inbound", max_depth=1)
    assert len(inbound) == 1
    assert inbound[0][1].node_id == "file:app.py"
