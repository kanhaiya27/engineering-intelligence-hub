"""
Tests for BGEEmbeddingModel
"""

import pytest
import torch

from knowledge.schemas.artifacts import ArtifactType, KnowledgeChunk
from knowledge.vector.embeddings import BGEEmbeddingModel


def test_bge_embedding_dimension_and_structure():
    model = BGEEmbeddingModel()
    assert model.embedding_dimension == 384
    assert model.active_device in ("cuda:0", "cpu")

    text = "Flask is a lightweight WSGI web application framework."
    emb = model.embed_text(text)

    assert isinstance(emb, list)
    assert len(emb) == 384
    assert all(isinstance(x, float) for x in emb)


def test_bge_embed_chunks():
    model = BGEEmbeddingModel()

    chunk1 = KnowledgeChunk(
        chunk_id="chunk-1",
        artifact_id="art-1",
        artifact_type=ArtifactType.SOURCE_CODE,
        repository="pallets/flask",
        content="def hello_world(): return 'Hello, World!'",
        chunk_index=0,
    )
    chunk2 = KnowledgeChunk(
        chunk_id="chunk-2",
        artifact_id="art-2",
        artifact_type=ArtifactType.MARKDOWN,
        repository="pallets/flask",
        content="# Routing in Flask\nUse @app.route decorator.",
        chunk_index=0,
    )

    embedded = model.embed_chunks([chunk1, chunk2])
    assert len(embedded) == 2
    assert embedded[0].embedding is not None
    assert len(embedded[0].embedding) == 384
    assert embedded[1].embedding is not None
    assert len(embedded[1].embedding) == 384


def test_bge_benchmark():
    model = BGEEmbeddingModel()
    results = model.benchmark(count=10)

    assert results["item_count"] == 10
    assert results["embedding_dim"] == 384
    assert results["total_time_seconds"] > 0
    assert "throughput_items_per_sec" in results
