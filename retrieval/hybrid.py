"""
Engineering Intelligence Hub — Hybrid Retriever (Dense + BM25)
==============================================================
Combines semantic vector search with keyword BM25 retrieval using weighted score fusion.
Provides the primary baseline retrieval engine for Phase-1 engineering RAG.
"""

from __future__ import annotations

import time
from typing import Dict, List, Optional

from core.logging import get_logger
from knowledge.schemas.tasks import RetrievedChunk, RetrievalResult, TaskClassification
from retrieval.base import BaseRetriever
from retrieval.bm25 import BM25Retriever
from retrieval.dense import DenseRetriever
from retrieval.reranker import apply_reranking
from retrieval.strategies import RetrievalStrategyConfig

logger = get_logger(__name__)


class HybridRetriever(BaseRetriever):
    """
    Hybrid retriever fusing dense vector search and sparse BM25 retrieval.
    """

    def __init__(
        self,
        dense_retriever: Optional[DenseRetriever] = None,
        sparse_retriever: Optional[BM25Retriever] = None,
    ) -> None:
        self.dense_retriever = dense_retriever or DenseRetriever()
        # A default BM25 is pointed at the dense retriever's own store/collection
        # so both halves index the same corpus. A bare BM25Retriever() would be
        # permanently empty, making every "hybrid" result silently dense-only.
        self.sparse_retriever = sparse_retriever or BM25Retriever(
            vector_store=self.dense_retriever.vector_store,
            collection_name=self.dense_retriever.collection_name,
            autoload=True,
        )

    @property
    def retriever_name(self) -> str:
        return "hybrid"

    def retrieve(
        self,
        query: str,
        strategy: RetrievalStrategyConfig,
        classification: Optional[TaskClassification] = None,
        task_id: str = "adhoc",
    ) -> RetrievalResult:
        start_time = time.perf_counter()

        dense_weight = strategy.dense_weight
        sparse_weight = strategy.sparse_weight

        # The score cut-off applies to the FUSED score only (WORK_PLAN C26, Step 2b). It used to
        # be applied to the dense cosine, the BM25 score and the fused score alike, so a chunk
        # found by one retriever only (fused <= its weight) had to clear e.g. 0.60 / 0.7 = 0.86
        # cosine: 13 of 28 dev/val hybrid tasks lost all labelled evidence.
        component_strategy = strategy.model_copy(update={"score_threshold": 0.0})

        # 1. Execute Dense Retrieval
        dense_result = self.dense_retriever.retrieve(
            query=query,
            strategy=component_strategy,
            classification=classification,
            task_id=task_id,
        )

        # 2. Execute BM25 Retrieval
        sparse_result = self.sparse_retriever.retrieve(
            query=query,
            strategy=component_strategy,
            classification=classification,
            task_id=task_id,
        )

        # 3. Fuse Scores
        combined_chunks: Dict[str, RetrievedChunk] = {}
        chunk_dense_scores: Dict[str, float] = {}
        chunk_sparse_scores: Dict[str, float] = {}

        for chunk in dense_result.chunks:
            combined_chunks[chunk.chunk_id] = chunk
            chunk_dense_scores[chunk.chunk_id] = chunk.score

        for chunk in sparse_result.chunks:
            if chunk.chunk_id not in combined_chunks:
                combined_chunks[chunk.chunk_id] = chunk
            chunk_sparse_scores[chunk.chunk_id] = chunk.score

        # Compute fused score for each chunk
        fused_scored_chunks: List[tuple[RetrievedChunk, float]] = []
        for chunk_id, chunk in combined_chunks.items():
            d_score = chunk_dense_scores.get(chunk_id, 0.0)
            s_score = chunk_sparse_scores.get(chunk_id, 0.0)

            # Weighted linear score fusion
            fused_score = (dense_weight * d_score) + (sparse_weight * s_score)

            # Store component scores in metadata
            chunk.metadata["dense_score"] = round(d_score, 4)
            chunk.metadata["sparse_score"] = round(s_score, 4)
            chunk.metadata["fused_score"] = round(fused_score, 4)
            chunk.score = round(fused_score, 4)

            if fused_score >= strategy.score_threshold:
                fused_scored_chunks.append((chunk, fused_score))

        # Sort by fused score descending
        fused_scored_chunks.sort(key=lambda x: x[1], reverse=True)

        # Build the candidate pool. When reranking is enabled the pool is the
        # full top_k so the cross-encoder has something to re-order; truncating
        # to max_context_chunks first would discard the very candidates
        # reranking exists to promote. Without reranking, behaviour is
        # unchanged from Phase-1.
        if strategy.enable_reranking:
            candidate_chunks = [item[0] for item in fused_scored_chunks[: strategy.top_k]]
        else:
            max_chunks = min(strategy.top_k, strategy.max_context_chunks)
            candidate_chunks = [item[0] for item in fused_scored_chunks[:max_chunks]]

        rerank_outcome = apply_reranking(
            query=query,
            chunks=candidate_chunks,
            strategy=strategy,
        )

        # Final context cap always applies, reranked or not.
        final_chunks = rerank_outcome.chunks[: strategy.max_context_chunks]

        latency_ms = (time.perf_counter() - start_time) * 1000.0

        return RetrievalResult(
            task_id=task_id,
            strategy_used=strategy.strategy_name,
            chunks=final_chunks,
            total_retrieved=len(final_chunks),
            retrieval_latency_ms=round(latency_ms, 2),
            metadata={
                "mode": "hybrid",
                "dense_weight": dense_weight,
                "sparse_weight": sparse_weight,
                "dense_retrieved": len(dense_result.chunks),
                "sparse_retrieved": len(sparse_result.chunks),
                **rerank_outcome.as_metadata(),
            },
        )
