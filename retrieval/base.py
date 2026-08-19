"""
Engineering Intelligence Hub — Abstract Retriever Interface
===========================================================
All concrete retriever implementations must inherit from BaseRetriever.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional

from knowledge.schemas.tasks import RetrievalResult, TaskClassification
from retrieval.strategies import RetrievalStrategyConfig


class BaseRetriever(ABC):
    """
    Abstract interface for all retrieval implementations.

    A retriever takes a query string + a task classification and returns
    a RetrievalResult containing ranked, relevant KnowledgeChunks.

    Phase-1 implementations:
      - DenseRetriever      : pure vector search
      - SparseRetriever     : BM25 / keyword search
      - HybridRetriever     : fused dense + sparse
      - GraphAugRetriever   : hybrid + graph context injection
    """

    @property
    @abstractmethod
    def retriever_name(self) -> str:
        """Human-readable name used in experiment logs."""
        ...

    @abstractmethod
    def retrieve(
        self,
        query: str,
        strategy: RetrievalStrategyConfig,
        classification: Optional[TaskClassification] = None,
    ) -> RetrievalResult:
        """
        Retrieve relevant knowledge chunks for a query.

        Parameters
        ----------
        query : str
            The user's query or a pre-processed query string.
        strategy : RetrievalStrategyConfig
            Full retrieval configuration for this call.
        classification : TaskClassification, optional
            Task classification output — used to apply repository and
            artifact-type filters automatically.

        Returns
        -------
        RetrievalResult
            Ranked list of retrieved chunks with latency metadata.
        """
        ...
