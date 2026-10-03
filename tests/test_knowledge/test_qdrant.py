"""
Tests for QdrantVectorStore
"""

import pytest

from knowledge.schemas.artifacts import ArtifactType, KnowledgeChunk
from knowledge.vector.qdrant import QdrantVectorStore


@pytest.fixture
def memory_vector_store():
    store = QdrantVectorStore(in_memory=True)
    store.connect()
    yield store
    store.disconnect()


def test_qdrant_collection_lifecycle(memory_vector_store):
    store = memory_vector_store
    coll_name = "test_collection"

    assert not store.collection_exists(coll_name)
    store.create_collection(coll_name, embedding_dimension=4)
    assert store.collection_exists(coll_name)

    # Upsert test
    chunks = [
        KnowledgeChunk(
            chunk_id="c1",
            artifact_id="a1",
            artifact_type=ArtifactType.SOURCE_CODE,
            repository="pallets/flask",
            content="def app_route(): pass",
            chunk_index=0,
            embedding=[0.1, 0.2, 0.3, 0.4],
            metadata={"language": "python"},
        ),
        KnowledgeChunk(
            chunk_id="c2",
            artifact_id="a2",
            artifact_type=ArtifactType.MARKDOWN,
            repository="fastapi/fastapi",
            content="# Routing Guide",
            chunk_index=0,
            embedding=[0.4, 0.3, 0.2, 0.1],
            metadata={"language": "markdown"},
        ),
    ]

    upserted = store.upsert(coll_name, chunks)
    assert upserted == 2
    assert store.count(coll_name) == 2

    # Search test
    results = store.search(coll_name, query_vector=[0.1, 0.2, 0.3, 0.4], top_k=2)
    assert len(results) == 2
    assert results[0][0].chunk_id == "c1"
    assert results[0][1] > 0.9

    # Filtered search test by repository
    flask_results = store.search(
        coll_name,
        query_vector=[0.1, 0.2, 0.3, 0.4],
        top_k=5,
        filter_metadata={"repository": "pallets/flask"},
    )
    assert len(flask_results) == 1
    assert flask_results[0][0].repository == "pallets/flask"

    # Delete test
    deleted = store.delete(coll_name, ["c1"])
    assert deleted == 1
    assert store.count(coll_name) == 1

    # Drop collection test
    assert store.delete_collection(coll_name) is True
    assert not store.collection_exists(coll_name)


def test_qdrant_docker_live_integration():
    """Test connection to running Docker Qdrant instance."""
    store = QdrantVectorStore(host="localhost", port=6333)
    try:
        store.connect()
        coll = "eih_integration_test"
        store.create_collection(coll, embedding_dimension=4)
        assert store.collection_exists(coll)

        chunk = KnowledgeChunk(
            chunk_id="live-c1",
            artifact_id="live-a1",
            artifact_type=ArtifactType.SOURCE_CODE,
            repository="pallets/flask",
            content="app = Flask(__name__)",
            chunk_index=0,
            embedding=[0.5, 0.5, 0.5, 0.5],
        )
        store.upsert(coll, [chunk])
        assert store.count(coll) == 1

        res = store.search(coll, query_vector=[0.5, 0.5, 0.5, 0.5], top_k=1)
        assert len(res) == 1
        assert res[0][0].chunk_id == "live-c1"

        store.delete_collection(coll)
    except Exception as e:
        pytest.skip(f"Docker Qdrant not accessible: {e}")
    finally:
        store.disconnect()
