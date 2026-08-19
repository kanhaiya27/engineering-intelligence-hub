"""
Engineering Intelligence Hub — BM25 Sparse Retriever
=====================================================
Retrieves relevant KnowledgeChunks via keyword matching using Okapi BM25.
Optimized for software engineering identifiers (function names, class names, file paths, errors).
"""

from __future__ import annotations

import re
import time
from typing import Any, Dict, List, Optional

from rank_bm25 import BM25Okapi

from core.logging import get_logger
from knowledge.schemas.artifacts import KnowledgeChunk
from knowledge.schemas.tasks import RetrievedChunk, RetrievalResult, TaskClassification
from retrieval.base import BaseRetriever
from retrieval.strategies import RetrievalStrategyConfig

logger = get_logger(__name__)


def code_aware_tokenize(text: str) -> List[str]:
    """
    Tokenizes prose and software engineering code identifiers.
    Splits camelCase, snake_case, dot.notation, path/slashes, and punctuation.
    """
    if not text:
        return []

    # Replace punctuation and code symbols with spaces except alphanumeric and underscores
    cleaned = re.sub(r"[^\w\s\.\/]", " ", text)
    tokens: List[str] = []

    for word in cleaned.split():
        word_lower = word.lower()
        tokens.append(word_lower)

        # Split snake_case
        if "_" in word:
            parts = word.split("_")
            tokens.extend([p.lower() for p in parts if p])

        # Split camelCase
        camel_parts = re.findall(r"[A-Z]?[a-z]+|[A-Z]+(?=[A-Z]|$)", word)
        if len(camel_parts) > 1:
            tokens.extend([cp.lower() for cp in camel_parts])

        # Split path or dot notation
        if "/" in word or "." in word:
            subparts = re.split(r"[\/\.]", word)
            tokens.extend([sp.lower() for sp in subparts if sp])

    return [t for t in tokens if len(t) > 1]


class BM25Retriever(BaseRetriever):
    """
    In-memory BM25 retriever for software engineering knowledge.
    """

    def __init__(self, chunks: Optional[List[KnowledgeChunk]] = None) -> None:
        self.chunks: List[KnowledgeChunk] = []
        self.corpus_tokens: List[List[str]] = []
        self.bm25: Optional[BM25Okapi] = None
        if chunks:
            self.index_chunks(chunks)

    @property
    def retriever_name(self) -> str:
        return "sparse"

    def index_chunks(self, chunks: List[KnowledgeChunk]) -> int:
        """Build or update BM25 index from chunks."""
        self.chunks = list(chunks)
        self.corpus_tokens = [code_aware_tokenize(c.content) for c in self.chunks]
        if self.corpus_tokens:
            self.bm25 = BM25Okapi(self.corpus_tokens)
        else:
            self.bm25 = None
        return len(self.chunks)

    def retrieve(
        self,
        query: str,
        strategy: RetrievalStrategyConfig,
        classification: Optional[TaskClassification] = None,
        task_id: str = "adhoc",
    ) -> RetrievalResult:
        start_time = time.perf_counter()

        if not self.bm25 or not self.chunks:
            return RetrievalResult(
                task_id=task_id,
                strategy_used=strategy.strategy_name,
                chunks=[],
                total_retrieved=0,
                retrieval_latency_ms=0.0,
                metadata={"mode": "sparse", "index_size": len(self.chunks)},
            )

        query_tokens = code_aware_tokenize(query)
        if not query_tokens:
            return RetrievalResult(
                task_id=task_id,
                strategy_used=strategy.strategy_name,
                chunks=[],
                total_retrieved=0,
                retrieval_latency_ms=0.0,
                metadata={"mode": "sparse", "index_size": len(self.chunks)},
            )

        raw_scores = self.bm25.get_scores(query_tokens)
        max_score = max(raw_scores) if len(raw_scores) > 0 and max(raw_scores) > 0 else 1.0

        # Pair chunks with normalized scores
        scored_pairs: List[tuple[KnowledgeChunk, float]] = []
        for idx, score in enumerate(raw_scores):
            if score <= 0.0:
                continue

            chunk = self.chunks[idx]

            # Apply filters
            if strategy.repository_filter and chunk.repository != strategy.repository_filter:
                continue
            if strategy.artifact_type_filter:
                art_type = chunk.artifact_type.value if hasattr(chunk.artifact_type, "value") else str(chunk.artifact_type)
                if art_type not in strategy.artifact_type_filter:
                    continue

            norm_score = score / max_score
            if norm_score >= strategy.score_threshold:
                scored_pairs.append((chunk, float(norm_score)))

        # Sort descending
        scored_pairs.sort(key=lambda x: x[1], reverse=True)
        top_pairs = scored_pairs[: strategy.top_k]

        latency_ms = (time.perf_counter() - start_time) * 1000.0

        retrieved_chunks: List[RetrievedChunk] = []
        for chunk, score in top_pairs:
            retrieved_chunks.append(
                RetrievedChunk(
                    chunk_id=chunk.chunk_id,
                    content=chunk.content,
                    score=round(score, 4),
                    artifact_id=chunk.artifact_id,
                    artifact_type=chunk.artifact_type.value if hasattr(chunk.artifact_type, "value") else str(chunk.artifact_type),
                    repository=chunk.repository,
                    source_path=chunk.metadata.get("file_path") or chunk.metadata.get("source_path"),
                    metadata=chunk.metadata,
                )
            )

        return RetrievalResult(
            task_id=task_id,
            strategy_used=strategy.strategy_name,
            chunks=retrieved_chunks,
            total_retrieved=len(retrieved_chunks),
            retrieval_latency_ms=round(latency_ms, 2),
            metadata={
                "mode": "sparse",
                "index_size": len(self.chunks),
            },
        )
