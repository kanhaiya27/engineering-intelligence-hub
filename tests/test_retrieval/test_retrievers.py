"""
Tests for DenseRetriever, BM25Retriever, and HybridRetriever
"""

import pytest

from knowledge.schemas.artifacts import ArtifactType, KnowledgeChunk
from knowledge.vector.embeddings import BGEEmbeddingModel
from knowledge.vector.qdrant import QdrantVectorStore
from retrieval.bm25 import BM25Retriever
from retrieval.dense import DenseRetriever
from retrieval.hybrid import HybridRetriever
from retrieval.strategies import RetrievalMode, RetrievalStrategyConfig


@pytest.fixture
def sample_indexed_knowledge():
    chunks = [
        KnowledgeChunk(
            chunk_id="flask-route-chunk",
            artifact_id="flask-src",
            artifact_type=ArtifactType.SOURCE_CODE,
            repository="pallets/flask",
            content="def route(self, rule: str, **options):\n    return self.add_url_rule(rule, endpoint, f, **options)",
            chunk_index=0,
            metadata={"symbol_name": "Flask.route", "file_path": "src/flask/app.py"},
        ),
        KnowledgeChunk(
            chunk_id="fastapi-app-chunk",
            artifact_id="fastapi-src",
            artifact_type=ArtifactType.SOURCE_CODE,
            repository="fastapi/fastapi",
            content="class FastAPI(Starlette):\n    def get(self, path: str, response_model: Any = None):\n        pass",
            chunk_index=0,
            metadata={"symbol_name": "FastAPI.get", "file_path": "fastapi/applications.py"},
        ),
        KnowledgeChunk(
            chunk_id="flask-doc-chunk",
            artifact_id="flask-doc",
            artifact_type=ArtifactType.MARKDOWN,
            repository="pallets/flask",
            content="# Quickstart Guide\nA minimal Flask application looks like this: app = Flask(__name__)",
            chunk_index=0,
            metadata={"section_title": "Quickstart Guide", "file_path": "docs/quickstart.rst"},
        ),
    ]
    return chunks


def test_bm25_retriever(sample_indexed_knowledge):
    bm25 = BM25Retriever(chunks=sample_indexed_knowledge)
    strat = RetrievalStrategyConfig(
        strategy_name="sparse_test",
        mode=RetrievalMode.SPARSE,
        top_k=2,
    )

    # Keyword search for route and add_url_rule
    res = bm25.retrieve("how does add_url_rule work in route?", strategy=strat)

    assert res.total_retrieved > 0
    assert res.chunks[0].chunk_id == "flask-route-chunk"
    assert res.chunks[0].score > 0.0


def test_dense_and_hybrid_retriever(sample_indexed_knowledge):
    # Setup in-memory Qdrant
    vec_store = QdrantVectorStore(in_memory=True)
    vec_store.connect()
    emb_model = BGEEmbeddingModel()

    # Embed and upsert chunks
    embedded_chunks = emb_model.embed_chunks(sample_indexed_knowledge)
    vec_store.upsert("eih_test_coll", embedded_chunks)

    dense_ret = DenseRetriever(
        embedding_model=emb_model,
        vector_store=vec_store,
        collection_name="eih_test_coll",
    )
    sparse_ret = BM25Retriever(chunks=sample_indexed_knowledge)

    hybrid_ret = HybridRetriever(
        dense_retriever=dense_ret,
        sparse_retriever=sparse_ret,
    )

    strat = RetrievalStrategyConfig(
        strategy_name="hybrid_test",
        mode=RetrievalMode.HYBRID,
        top_k=3,
        dense_weight=0.7,
        sparse_weight=0.3,
    )

    res = hybrid_ret.retrieve("minimal Flask application quickstart", strategy=strat)

    assert res.total_retrieved > 0
    # Top result should be the Flask quickstart guide
    top_chunk = res.chunks[0]
    assert "Flask" in top_chunk.content
    assert top_chunk.score > 0.5
    assert "dense_score" in top_chunk.metadata
    assert "sparse_score" in top_chunk.metadata

    vec_store.disconnect()
