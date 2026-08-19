"""
FastAPI Router for Knowledge Retrieval
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from core.logging import get_logger
from knowledge.schemas.tasks import RetrievalResult
from knowledge.vector.embeddings import BGEEmbeddingModel
from knowledge.vector.qdrant import QdrantVectorStore
from retrieval.dense import DenseRetriever
from retrieval.strategies import RetrievalMode, RetrievalStrategyConfig

logger = get_logger(__name__)

router = APIRouter(prefix="/retrieve", tags=["Retrieval"])

_dense_retriever: Optional[DenseRetriever] = None


def get_retriever() -> DenseRetriever:
    global _dense_retriever
    if _dense_retriever is None:
        emb_model = BGEEmbeddingModel()
        vec_store = QdrantVectorStore()
        vec_store.connect()
        _dense_retriever = DenseRetriever(embedding_model=emb_model, vector_store=vec_store)
    return _dense_retriever


class RetrieveRequest(BaseModel):
    query: str
    repository: Optional[str] = None
    top_k: int = 5
    score_threshold: float = 0.0
    mode: str = "dense"


@router.post("", response_model=RetrievalResult)
async def retrieve_endpoint(req: RetrieveRequest):
    retriever = get_retriever()

    try:
        strat = RetrievalStrategyConfig(
            strategy_name=f"api_{req.mode}",
            mode=RetrievalMode.DENSE,
            top_k=req.top_k,
            score_threshold=req.score_threshold,
            repository_filter=req.repository,
        )
        result = retriever.retrieve(query=req.query, strategy=strat)
        return result
    except Exception as e:
        logger.error(f"Retrieval failed: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))
