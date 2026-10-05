"""Hybrid retrieval applies the score cut-off to the fused score only (WORK_PLAN C26)."""

from __future__ import annotations

from unittest.mock import MagicMock

from knowledge.schemas.tasks import RetrievalResult, RetrievedChunk
from retrieval.hybrid import HybridRetriever
from retrieval.strategies import RetrievalMode, RetrievalStrategyConfig


def _res(*chunks):
    return RetrievalResult(task_id="t", strategy_used="x", chunks=list(chunks), total_retrieved=len(chunks))


def _chunk(cid, score):
    return RetrievedChunk(chunk_id=cid, content="c", score=score, source_path="a.py", metadata={})


def test_components_run_without_cutoff_and_fused_cutoff_decides():
    h = object.__new__(HybridRetriever)
    h.dense_retriever, h.sparse_retriever = MagicMock(), MagicMock()
    # dense-only chunk with cosine 0.5 -> fused 0.35; BM25-only chunk 0.6 -> fused 0.18
    h.dense_retriever.retrieve.return_value = _res(_chunk("d", 0.5))
    h.sparse_retriever.retrieve.return_value = _res(_chunk("s", 0.6))
    strat = RetrievalStrategyConfig(strategy_name="hybrid", mode=RetrievalMode.HYBRID, top_k=7,
                                    max_context_chunks=7, score_threshold=0.25, dense_weight=0.7, sparse_weight=0.3)
    out = h.retrieve(query="q", strategy=strat)
    for comp in (h.dense_retriever, h.sparse_retriever):
        assert comp.retrieve.call_args.kwargs["strategy"].score_threshold == 0.0
    assert [c.chunk_id for c in out.chunks] == ["d"]  # 0.35 passes 0.25, 0.18 does not
    assert out.chunks[0].metadata["fused_score"] == 0.35
