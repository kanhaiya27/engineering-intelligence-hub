"""
FastAPI Router for Grounded Engineering Query & RAG
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException, status

from core.logging import get_logger
from generation.rag import BaselineRAGPipeline
from knowledge.schemas.tasks import EngTaskRequest, EngTaskResponse
from knowledge.vector.embeddings import BGEEmbeddingModel
from knowledge.vector.qdrant import QdrantVectorStore
from retrieval.dense import DenseRetriever

logger = get_logger(__name__)

router = APIRouter(prefix="/query", tags=["Query"])

_rag_pipeline: Optional[BaselineRAGPipeline] = None


def get_rag_pipeline() -> BaselineRAGPipeline:
    global _rag_pipeline
    if _rag_pipeline is None:
        emb_model = BGEEmbeddingModel()
        vec_store = QdrantVectorStore()
        vec_store.connect()
        retriever = DenseRetriever(embedding_model=emb_model, vector_store=vec_store)
        _rag_pipeline = BaselineRAGPipeline(retriever=retriever)
    return _rag_pipeline


@router.post("", response_model=EngTaskResponse)
async def query_endpoint(req: EngTaskRequest):
    pipeline = get_rag_pipeline()
    try:
        response = pipeline.execute(request=req)
        return response
    except Exception as e:
        logger.error(f"Query generation failed: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))
