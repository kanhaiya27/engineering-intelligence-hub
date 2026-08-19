"""
Engineering Intelligence Hub — Abstract Vector Store Interface
==============================================================
Defines the contract for all vector store backends (Qdrant, Chroma, etc.).

Implementation guide
--------------------
Phase-1 will add concrete implementations under knowledge/vector/:
  - QdrantVectorStore (recommended — supports hybrid search natively)
  - ChromaVectorStore (lightweight alternative for local dev)

The interface is intentionally minimal. Richer features (filtered search,
payload indexing, collection management) are exposed as optional methods
that implementors can override.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Tuple

from knowledge.schemas.artifacts import KnowledgeChunk


class BaseVectorStore(ABC):
    """
    Abstract interface for a vector knowledge store.

    Lifecycle:
        1. Instantiate with connection config.
        2. Call connect() to establish a connection.
        3. Use upsert / search / delete as needed.
        4. Call disconnect() when done.
    """

    @property
    @abstractmethod
    def store_name(self) -> str:
        """Human-readable name of this vector store backend."""
        ...

    @abstractmethod
    def connect(self) -> None:
        """Establish connection to the vector store."""
        ...

    @abstractmethod
    def disconnect(self) -> None:
        """Close the connection to the vector store."""
        ...

    @abstractmethod
    def collection_exists(self, collection_name: str) -> bool:
        """Return True if the named collection exists."""
        ...

    @abstractmethod
    def create_collection(
        self,
        collection_name: str,
        embedding_dimension: int,
        distance_metric: str = "cosine",
    ) -> None:
        """
        Create a new collection.

        Parameters
        ----------
        collection_name : str
        embedding_dimension : int
            Dimensionality of embedding vectors.
        distance_metric : str
            'cosine' | 'dot' | 'euclidean'
        """
        ...

    @abstractmethod
    def upsert(
        self,
        collection_name: str,
        chunks: List[KnowledgeChunk],
    ) -> int:
        """
        Insert or update chunks in the collection.
        Chunks must have embedding populated.

        Returns
        -------
        int
            Number of chunks successfully upserted.
        """
        ...

    @abstractmethod
    def search(
        self,
        collection_name: str,
        query_vector: List[float],
        top_k: int = 5,
        score_threshold: float = 0.0,
        filter_metadata: Optional[Dict[str, Any]] = None,
    ) -> List[Tuple[KnowledgeChunk, float]]:
        """
        Perform approximate nearest-neighbour search.

        Parameters
        ----------
        collection_name : str
        query_vector : List[float]
            Query embedding.
        top_k : int
            Maximum results to return.
        score_threshold : float
            Minimum similarity score — results below this are discarded.
        filter_metadata : dict, optional
            Metadata-level filter (provider-specific implementation).

        Returns
        -------
        List[Tuple[KnowledgeChunk, float]]
            (chunk, score) pairs sorted by descending score.
        """
        ...

    @abstractmethod
    def delete(self, collection_name: str, chunk_ids: List[str]) -> int:
        """
        Delete chunks by ID.

        Returns
        -------
        int
            Number of chunks deleted.
        """
        ...

    @abstractmethod
    def count(self, collection_name: str) -> int:
        """Return the number of chunks in the collection."""
        ...

    def keyword_search(
        self,
        collection_name: str,
        query: str,
        top_k: int = 5,
        filter_metadata: Optional[Dict[str, Any]] = None,
    ) -> List[Tuple[KnowledgeChunk, float]]:
        """
        BM25 / full-text keyword search (optional — not all backends support this).
        Override in backends that natively support sparse retrieval.
        """
        raise NotImplementedError(
            f"{self.__class__.__name__} does not support keyword_search(). "
            "Use a hybrid retriever or a dedicated keyword index."
        )
