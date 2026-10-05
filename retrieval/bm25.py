"""
Engineering Intelligence Hub — BM25 Sparse Retriever
=====================================================
Retrieves relevant KnowledgeChunks via keyword matching using Okapi BM25.
Optimized for software engineering identifiers (function names, class names, file paths, errors).
"""

from __future__ import annotations

import re
import time
from typing import Any, List, Optional

from rank_bm25 import BM25Plus

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
    In-memory BM25 retriever for software engineering knowledge using BM25Plus.
    """

    def __init__(
        self,
        chunks: Optional[List[KnowledgeChunk]] = None,
        vector_store: Optional[Any] = None,
        collection_name: Optional[str] = None,
        autoload: bool = False,
    ) -> None:
        """
        Build a BM25 index over knowledge chunks.

        Corpus sources, in precedence order:
          1. `chunks` passed directly (unit tests, explicit control)
          2. `vector_store` + `collection_name` with `autoload=True` — pulls the
             same corpus the dense index holds

        WHY autoload EXISTS: ingestion persists chunks to Qdrant only. This index
        lives in process memory with no persistence of its own, so a bare
        `BM25Retriever()` is permanently empty. Every strategy with a non-zero
        `sparse_weight` then silently degrades to dense-only, and the strategies
        with `sparse_weight=1.0` (`sparse`, `incident_sparse`) return nothing at
        all. Retrieval reported as "hybrid" must actually be hybrid.
        """
        self.chunks: List[KnowledgeChunk] = []
        self.corpus_tokens: List[List[str]] = []
        self.bm25: Optional[BM25Plus] = None
        self._vector_store = vector_store
        self._collection_name = collection_name
        self._autoload = autoload
        self._load_attempted = False

        if chunks:
            self.index_chunks(chunks)
            self._load_attempted = True

    def _ensure_corpus(self) -> None:
        """
        Lazily populate the corpus on first retrieval.

        Loading lazily rather than in __init__ keeps construction cheap and keeps
        the hermetic test suite from reaching for Qdrant. The attempt is made at
        most once, so a store that is down logs a single error instead of one per
        query.
        """
        if self._load_attempted or not self._autoload:
            return
        self._load_attempted = True
        if self._vector_store is not None and self._collection_name:
            self.load_from_vector_store(self._vector_store, self._collection_name)

    def refresh(self) -> int:
        """Force a corpus reload — call after ingesting new content."""
        self._load_attempted = True
        return self.load_from_vector_store()

    @property
    def retriever_name(self) -> str:
        return "sparse"

    @property
    def is_populated(self) -> bool:
        """True when the index holds a usable corpus."""
        return self.bm25 is not None and len(self.chunks) > 0

    def load_from_vector_store(
        self,
        vector_store: Optional[Any] = None,
        collection_name: Optional[str] = None,
    ) -> int:
        """
        Populate the index from the vector store's collection.

        Returns the number of chunks indexed — 0 means the sparse half of hybrid
        retrieval is inert, which is logged as an error rather than passing
        quietly, since the failure is otherwise invisible in the results.
        """
        store = vector_store or self._vector_store
        collection = collection_name or self._collection_name

        if store is None or not collection:
            logger.error(
                "BM25 load_from_vector_store called without a store/collection. "
                "Sparse retrieval will return nothing."
            )
            return 0

        try:
            chunks = store.scroll_all(collection_name=collection)
        except Exception as exc:  # noqa: BLE001 - store unreachable or no scroll support
            logger.error(
                f"BM25 corpus load from '{collection}' failed: {exc}. "
                "Sparse retrieval will return nothing and any 'hybrid' result "
                "will in fact be dense-only."
            )
            return 0

        indexed = self.index_chunks(chunks)
        if indexed == 0:
            logger.error(
                f"BM25 corpus load from '{collection}' produced 0 chunks. "
                "Collection is empty or not yet ingested."
            )
        else:
            logger.info(f"BM25 indexed {indexed} chunks from collection '{collection}'.")
        return indexed

    def index_chunks(self, chunks: List[KnowledgeChunk]) -> int:
        """Build or update BM25 index from chunks."""
        self.chunks = list(chunks)
        self.corpus_tokens = []
        for c in self.chunks:
            # Combine content with symbol name, file path, and repo for comprehensive matching
            meta_parts = [
                c.content,
                c.metadata.get("symbol_name", ""),
                c.metadata.get("file_path", ""),
                c.metadata.get("section_title", ""),
                c.repository,
            ]
            full_text = " ".join(p for p in meta_parts if p)
            self.corpus_tokens.append(code_aware_tokenize(full_text))

        if self.corpus_tokens:
            self.bm25 = BM25Plus(self.corpus_tokens)
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

        self._ensure_corpus()

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
                    # start/end lines are top-level chunk fields, not metadata: without
                    # copying them the prompt showed no line ranges (so no [file:Lx-Ly]
                    # citations were possible) and the citation check had nothing to
                    # compare cited lines against.
                    metadata={**chunk.metadata, "start_line": chunk.start_line, "end_line": chunk.end_line},
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
