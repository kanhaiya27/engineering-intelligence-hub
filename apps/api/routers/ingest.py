"""
FastAPI Router for Repository & File Ingestion
"""

from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from core.config import settings
from core.logging import get_logger
from ingestion.loaders.file_loader import FileIngestionSource
from ingestion.loaders.github_loader import GitHubRepositoryIngestionSource
from ingestion.processors.normalizer import ArtifactNormalizer
from knowledge.schemas.artifacts import BaseArtifact, KnowledgeChunk
from knowledge.vector.embeddings import BGEEmbeddingModel
from knowledge.vector.qdrant import QdrantVectorStore

logger = get_logger(__name__)

router = APIRouter(prefix="/ingest", tags=["Ingestion"])

# Global shared resources for API
_embedding_model: Optional[BGEEmbeddingModel] = None
_vector_store: Optional[QdrantVectorStore] = None
_normalizer: Optional[ArtifactNormalizer] = None


def get_services():
    global _embedding_model, _vector_store, _normalizer
    if _embedding_model is None:
        _embedding_model = BGEEmbeddingModel()
    if _vector_store is None:
        _vector_store = QdrantVectorStore()
        _vector_store.connect()
    if _normalizer is None:
        _normalizer = ArtifactNormalizer()
    return _embedding_model, _vector_store, _normalizer


class IngestRepositoryRequest(BaseModel):
    repository: str = Field(description="Repository name or slug (e.g. pallets/flask)")
    local_path: Optional[str] = Field(default=None, description="Local path if already cloned")
    clone_url: Optional[str] = Field(default=None, description="Git clone URL")
    commit_or_tag: Optional[str] = Field(default=None, description="Target commit SHA or tag")
    collection_name: Optional[str] = Field(default=None)


class IngestRepositoryResponse(BaseModel):
    repository: str
    artifacts_ingested: int
    chunks_indexed: int
    collection_name: str
    status: str


class IngestFileRequest(BaseModel):
    repository: str
    file_path: str
    content: str
    artifact_type: str = "source_code"
    collection_name: Optional[str] = Field(default=None)


@router.post("/repository", response_model=IngestRepositoryResponse)
async def ingest_repository(req: IngestRepositoryRequest):
    emb_model, vec_store, normalizer = get_services()

    try:
        if req.local_path:
            loader = FileIngestionSource(
                root_dir=req.local_path,
                repository_id=req.repository,
                commit_sha=req.commit_or_tag,
            )
        else:
            loader = GitHubRepositoryIngestionSource(
                repository=req.repository,
                clone_url=req.clone_url,
                target_commit_or_tag=req.commit_or_tag,
            )

        artifacts = list(loader.load())
        chunks: List[KnowledgeChunk] = []
        for art in artifacts:
            art_chunks = normalizer.process_artifact(art)
            chunks.extend(art_chunks)

        if chunks:
            emb_model.embed_chunks(chunks)
            vec_store.upsert(req.collection_name, chunks)

        return IngestRepositoryResponse(
            repository=req.repository,
            artifacts_ingested=len(artifacts),
            chunks_indexed=len(chunks),
            collection_name=req.collection_name or settings.vector_store.collection_name,
            status="completed",
        )
    except Exception as e:
        logger.error(f"Failed to ingest repository {req.repository}: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.post("/file")
async def ingest_file(req: IngestFileRequest):
    emb_model, vec_store, normalizer = get_services()

    try:
        art = BaseArtifact(
            artifact_id=f"{req.repository}:{req.file_path}:direct",
            artifact_type=req.artifact_type,  # type: ignore[arg-type]
            repository=req.repository,
            source_path=req.file_path,
            raw_content=req.content,
        )
        chunks = normalizer.process_artifact(art)
        if chunks:
            emb_model.embed_chunks(chunks)
            vec_store.upsert(req.collection_name or settings.vector_store.collection_name, chunks)

        return {
            "status": "completed",
            "artifact_id": art.artifact_id,
            "chunks_indexed": len(chunks),
        }
    except Exception as e:
        logger.error(f"Failed to ingest file: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))
