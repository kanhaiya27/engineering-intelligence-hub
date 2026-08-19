"""
Engineering Intelligence Hub — Dense Vector Retriever
======================================================
Retrieves relevant KnowledgeChunks via semantic embedding similarity in Qdrant.
"""

from __future__ import annotations

import time
from typing import Any, Dict, List, Optional

from core.config import settings
from core.logging import get_logger
from knowledge.schemas.tasks import RetrievedChunk, RetrievalResult, TaskClassification
from knowledge.vector.base import BaseVectorStore
from knowledge.vector.embeddings import BGEEmbeddingModel
from knowledge.vector.qdrant import QdrantVectorStore
from retrieval.base import BaseRetriever
from retrieval.strategies import RetrievalStrategyConfig

logger = get_logger(__name__)


class DenseRetriever(BaseRetriever):
    """
    Pure vector similarity retriever backed by BGE embeddings and Qdrant.
    """

    def __init__(
        self,
        embedding_model: Optional[BGEEmbeddingModel] = None,
        vector_store: Optional[BaseVectorStore] = None,
        collection_name: Optional[str] = None,
    ) -> None:
        self.embedding_model = embedding_model or BGEEmbeddingModel()
        self.vector_store = vector_store or QdrantVectorStore()
        self.collection_name = collection_name or settings.vector_store.collection_name

    @property
    def retriever_name(self) -> str:
        return "dense"

    def retrieve(
        self,
        query: str,
        strategy: RetrievalStrategyConfig,
        classification: Optional[TaskClassification] = None,
        task_id: str = "adhoc",
    ) -> RetrievalResult:
        start_time = time.perf_counter()

        # 1. Embed query
        query_vector = self.embedding_model.embed_text(query)

        # 2. Build filters
        filter_metadata: Dict[str, Any] = {}
        if strategy.repository_filter:
            filter_metadata["repository"] = strategy.repository_filter
        if strategy.artifact_type_filter:
            filter_metadata["artifact_type"] = strategy.artifact_type_filter

        # 3. Query Qdrant
        search_results = self.vector_store.search(
            collection_name=self.collection_name,
            query_vector=query_vector,
            top_k=strategy.top_k,
            score_threshold=strategy.score_threshold,
            filter_metadata=filter_metadata if filter_metadata else None,
        )

        latency_ms = (time.perf_counter() - start_time) * 1000.0

        # 4. Format chunks
        retrieved_chunks: List[RetrievedChunk] = []
        for chunk, score in search_results:
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
                "mode": "dense",
                "embedding_model": self.embedding_model.model_name,
                "vector_store": self.vector_store.store_name,
            },
        )
