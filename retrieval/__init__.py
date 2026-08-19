"""
Engineering Intelligence Hub — Retrieval Module
"""

from retrieval.base import BaseRetriever
from retrieval.router import RetrievalRouter
from retrieval.strategies import RetrievalMode, RetrievalStrategyConfig

__all__ = [
    # Phase-1 (unchanged)
    "BaseRetriever",
    "RetrievalRouter",
    "RetrievalMode",
    "RetrievalStrategyConfig",
    # Phase-2 M3 symbols — imported lazily to avoid torch/qdrant at test time
    # Import directly from their submodules when needed:
    #   from retrieval.adaptive import AdaptiveRetrievalPipeline, ExperimentMode
    #   from retrieval.graph_augmented import GraphAugmentedRetriever
    #   from retrieval.policy import AdaptiveRetrievalPolicy
    #   from retrieval.bm25 import BM25Retriever
    #   from retrieval.dense import DenseRetriever
    #   from retrieval.hybrid import HybridRetriever
]
