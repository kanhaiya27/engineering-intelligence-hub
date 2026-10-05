"""Retrieved chunks carry their line ranges into the prompt and the citation check (fixed 2026-10-05)."""

from __future__ import annotations

from types import SimpleNamespace

from generation.quality_rag import QualityAwareRAGPipeline
from knowledge.schemas.artifacts import ArtifactType, KnowledgeChunk
from retrieval.bm25 import BM25Retriever
from retrieval.dense import DenseRetriever
from retrieval.strategies import RetrievalMode, RetrievalStrategyConfig

CHUNK = KnowledgeChunk(chunk_id="flask:src/flask/ctx.py:chunk:7", artifact_id="flask:src/flask/ctx.py",
                       artifact_type=ArtifactType.SOURCE_CODE, repository="pallets/flask",
                       content="class AppContext:\n    def push(self) -> None:\n        pass", chunk_index=7,
                       start_line=287, end_line=307, metadata={"file_path": "src/flask/ctx.py", "symbol_name": "AppContext"})


def strategy(mode):
    return RetrievalStrategyConfig(strategy_name="t", mode=mode, top_k=1)


def assert_lines(result):
    c = result.chunks[0]
    assert (c.metadata["start_line"], c.metadata["end_line"]) == (287, 307)
    assert "File: src/flask/ctx.py (Lines 287-307)" in QualityAwareRAGPipeline._build_context_prompt(None, [c])


def test_bm25_chunks_carry_line_ranges():
    bm25 = BM25Retriever()
    bm25.index_chunks([CHUNK])
    assert_lines(bm25.retrieve(query="AppContext push", strategy=strategy(RetrievalMode.SPARSE), task_id="t"))


def test_dense_chunks_carry_line_ranges():
    embedder = SimpleNamespace(embed_text=lambda q: [0.0] * 384, model_name="fake")
    store = SimpleNamespace(search=lambda *a, **k: [(CHUNK, 0.9)], store_name="fake")
    dense = DenseRetriever(embedding_model=embedder, vector_store=store, collection_name="c")
    assert_lines(dense.retrieve(query="AppContext push", strategy=strategy(RetrievalMode.DENSE), task_id="t"))
