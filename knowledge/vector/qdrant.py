"""
Engineering Intelligence Hub — Qdrant Vector Store Implementation
==================================================================
Concrete implementation of BaseVectorStore backed by Qdrant vector database.

Supports:
- Remote Qdrant server connection (Docker / Cloud) and in-memory test mode.
- Vector upsert with full KnowledgeChunk payload indexing.
- Exact and approximate nearest neighbour search with cosine/dot similarity via query_points.
- Metadata filtering (repository, artifact_type, file_path).
- Batch operations with robust error handling.
"""

from __future__ import annotations

import uuid
from typing import Any, Dict, List, Optional, Tuple

from qdrant_client import QdrantClient
from qdrant_client.http import models as qmodels

from core.config import settings
from core.logging import get_logger
from knowledge.schemas.artifacts import ArtifactType, KnowledgeChunk
from knowledge.vector.base import BaseVectorStore

logger = get_logger(__name__)


def _uuid_from_string(val: str) -> str:
    """Generate a deterministic UUID string from an arbitrary chunk_id."""
    return str(uuid.uuid5(uuid.NAMESPACE_DNS, val))


class QdrantVectorStore(BaseVectorStore):
    """
    Qdrant vector store backend.
    """

    def __init__(
        self,
        host: Optional[str] = None,
        port: Optional[int] = None,
        url: Optional[str] = None,
        api_key: Optional[str] = None,
        in_memory: bool = False,
    ) -> None:
        self.host = host or settings.vector_store.host
        self.port = port or settings.vector_store.port
        self.url = url
        self.api_key = api_key
        self.in_memory = in_memory
        self.client: Optional[QdrantClient] = None

    @property
    def store_name(self) -> str:
        return "qdrant"

    def connect(self) -> None:
        """Establish connection to Qdrant."""
        if self.in_memory:
            logger.info("Connecting to in-memory Qdrant instance...")
            self.client = QdrantClient(":memory:")
        elif self.url:
            logger.info(f"Connecting to Qdrant at {self.url}...")
            self.client = QdrantClient(url=self.url, api_key=self.api_key)
        else:
            logger.info(f"Connecting to Qdrant at {self.host}:{self.port}...")
            self.client = QdrantClient(host=self.host, port=self.port, api_key=self.api_key)

    def disconnect(self) -> None:
        """Close connection to Qdrant."""
        if self.client is not None:
            self.client.close()
            self.client = None

    def _ensure_connected(self) -> QdrantClient:
        if self.client is None:
            self.connect()
        assert self.client is not None
        return self.client

    def collection_exists(self, collection_name: str) -> bool:
        """Return True if the named collection exists."""
        client = self._ensure_connected()
        try:
            return client.collection_exists(collection_name)
        except Exception as e:
            logger.warning(f"Error checking if collection '{collection_name}' exists: {e}")
            return False

    def create_collection(
        self,
        collection_name: str,
        embedding_dimension: int = 384,
        distance_metric: str = "cosine",
    ) -> None:
        """Create a new Qdrant collection if it does not already exist."""
        client = self._ensure_connected()

        metric_map = {
            "cosine": qmodels.Distance.COSINE,
            "dot": qmodels.Distance.DOT,
            "euclidean": qmodels.Distance.EUCLID,
        }
        qdistance = metric_map.get(distance_metric.lower(), qmodels.Distance.COSINE)

        if not self.collection_exists(collection_name):
            logger.info(f"Creating Qdrant collection '{collection_name}' (dim={embedding_dimension}, metric={distance_metric})...")
            client.create_collection(
                collection_name=collection_name,
                vectors_config=qmodels.VectorParams(
                    size=embedding_dimension,
                    distance=qdistance,
                ),
            )
            # Create payload index for repository and artifact_type if remote server
            if not self.in_memory:
                try:
                    client.create_payload_index(
                        collection_name=collection_name,
                        field_name="repository",
                        field_schema=qmodels.PayloadSchemaType.KEYWORD,
                    )
                    client.create_payload_index(
                        collection_name=collection_name,
                        field_name="artifact_type",
                        field_schema=qmodels.PayloadSchemaType.KEYWORD,
                    )
                except Exception as e:
                    logger.debug(f"Payload index creation note: {e}")

    def upsert(
        self,
        collection_name: str,
        chunks: List[KnowledgeChunk],
    ) -> int:
        """Upsert KnowledgeChunks into collection."""
        if not chunks:
            return 0

        client = self._ensure_connected()

        # Ensure collection exists
        if not self.collection_exists(collection_name):
            first_emb = next((c.embedding for c in chunks if c.embedding is not None), None)
            dim = len(first_emb) if first_emb else 384
            self.create_collection(collection_name, embedding_dimension=dim)

        points: List[qmodels.PointStruct] = []
        for chunk in chunks:
            if chunk.embedding is None:
                raise ValueError(f"Chunk '{chunk.chunk_id}' has no embedding vector.")

            point_id = _uuid_from_string(chunk.chunk_id)
            payload = {
                "chunk_id": chunk.chunk_id,
                "artifact_id": chunk.artifact_id,
                "artifact_type": chunk.artifact_type.value if hasattr(chunk.artifact_type, "value") else str(chunk.artifact_type),
                "repository": chunk.repository,
                "content": chunk.content,
                "chunk_index": chunk.chunk_index,
                "total_chunks": chunk.total_chunks,
                "start_line": chunk.start_line,
                "end_line": chunk.end_line,
                "token_count": chunk.token_count,
                "metadata": chunk.metadata,
            }
            points.append(
                qmodels.PointStruct(
                    id=point_id,
                    vector=chunk.embedding,
                    payload=payload,
                )
            )

        # Batch upsert
        client.upsert(
            collection_name=collection_name,
            points=points,
            wait=True,
        )
        return len(points)

    def _build_filter(self, filter_metadata: Optional[Dict[str, Any]]) -> Optional[qmodels.Filter]:
        """Convert metadata dictionary into Qdrant filter conditions."""
        if not filter_metadata:
            return None

        must_conditions: List[qmodels.Condition] = []
        for k, v in filter_metadata.items():
            if v is None:
                continue
            if isinstance(v, list):
                must_conditions.append(
                    qmodels.FieldCondition(
                        key=k,
                        match=qmodels.MatchAny(any=v),
                    )
                )
            else:
                must_conditions.append(
                    qmodels.FieldCondition(
                        key=k,
                        match=qmodels.MatchValue(value=v),
                    )
                )

        return qmodels.Filter(must=must_conditions) if must_conditions else None

    def search(
        self,
        collection_name: str,
        query_vector: List[float],
        top_k: int = 5,
        score_threshold: float = 0.0,
        filter_metadata: Optional[Dict[str, Any]] = None,
    ) -> List[Tuple[KnowledgeChunk, float]]:
        """Perform similarity search via query_points."""
        client = self._ensure_connected()

        if not self.collection_exists(collection_name):
            return []

        qfilter = self._build_filter(filter_metadata)

        # Support both modern query_points (Qdrant >=1.10) and legacy search (Qdrant <1.10)
        try:
            if hasattr(client, "query_points"):
                response = client.query_points(
                    collection_name=collection_name,
                    query=query_vector,
                    limit=top_k,
                    score_threshold=score_threshold if score_threshold > 0.0 else None,
                    query_filter=qfilter,
                    with_payload=True,
                )
                scored_points = response.points
            elif hasattr(client, "search"):
                scored_points = client.search(
                    collection_name=collection_name,
                    query_vector=query_vector,
                    limit=top_k,
                    score_threshold=score_threshold if score_threshold > 0.0 else None,
                    query_filter=qfilter,
                    with_payload=True,
                )
            else:
                scored_points = []
        except Exception as e:
            # Fallback to search if query_points returned 404
            if hasattr(client, "search"):
                scored_points = client.search(
                    collection_name=collection_name,
                    query_vector=query_vector,
                    limit=top_k,
                    score_threshold=score_threshold if score_threshold > 0.0 else None,
                    query_filter=qfilter,
                    with_payload=True,
                )
            else:
                raise e

        output: List[Tuple[KnowledgeChunk, float]] = []
        for scored_point in scored_points:
            payload = scored_point.payload or {}
            chunk = KnowledgeChunk(
                chunk_id=payload.get("chunk_id", str(scored_point.id)),
                artifact_id=payload.get("artifact_id", ""),
                artifact_type=ArtifactType(payload.get("artifact_type", "source_code")),
                repository=payload.get("repository", ""),
                content=payload.get("content", ""),
                chunk_index=payload.get("chunk_index", 0),
                total_chunks=payload.get("total_chunks"),
                start_line=payload.get("start_line"),
                end_line=payload.get("end_line"),
                token_count=payload.get("token_count"),
                metadata=payload.get("metadata", {}),
            )
            output.append((chunk, float(scored_point.score)))

        return output

    def scroll_all(
        self,
        collection_name: str,
        batch_size: int = 1000,
        repository: Optional[str] = None,
    ) -> List[KnowledgeChunk]:
        """
        Return every chunk in a collection, without vectors.

        Exists so the sparse (BM25) index can be built from the same corpus the
        dense index holds. Ingestion writes chunks to Qdrant only; BM25 keeps its
        index in process memory and has no persistence, so without this the sparse
        half of hybrid retrieval is permanently empty and every "hybrid" result is
        silently dense-only.

        Vectors are excluded (`with_vectors=False`) — BM25 needs the text, not the
        embeddings, and pulling 384-float vectors for the whole corpus is wasted
        bandwidth and memory.

        Note on scale: this materialises the full corpus in memory. That is fine at
        the tens-of-thousands-of-chunks range this project operates in, and the
        planned scalability study (10K -> 500K chunks) is precisely the experiment
        that will establish where it stops being fine.
        """
        client = self._ensure_connected()

        if not self.collection_exists(collection_name):
            logger.warning(
                f"Collection '{collection_name}' does not exist — returning no chunks."
            )
            return []

        qfilter = self._build_filter({"repository": repository} if repository else None)

        chunks: List[KnowledgeChunk] = []
        offset = None
        while True:
            points, offset = client.scroll(
                collection_name=collection_name,
                limit=batch_size,
                offset=offset,
                with_payload=True,
                with_vectors=False,
                scroll_filter=qfilter,
            )
            for point in points:
                payload = point.payload or {}
                chunks.append(
                    KnowledgeChunk(
                        chunk_id=payload.get("chunk_id", str(point.id)),
                        artifact_id=payload.get("artifact_id", ""),
                        artifact_type=ArtifactType(payload.get("artifact_type", "source_code")),
                        repository=payload.get("repository", ""),
                        content=payload.get("content", ""),
                        chunk_index=payload.get("chunk_index", 0),
                        total_chunks=payload.get("total_chunks"),
                        start_line=payload.get("start_line"),
                        end_line=payload.get("end_line"),
                        token_count=payload.get("token_count"),
                        metadata=payload.get("metadata", {}),
                    )
                )
            if offset is None:
                break

        logger.info(
            f"Scrolled {len(chunks)} chunks from '{collection_name}'"
            + (f" (repository={repository})" if repository else "")
        )
        return chunks

    def delete(self, collection_name: str, chunk_ids: List[str]) -> int:
        """Delete chunks by ID."""
        if not chunk_ids:
            return 0
        client = self._ensure_connected()
        if not self.collection_exists(collection_name):
            return 0

        point_ids = [_uuid_from_string(cid) for cid in chunk_ids]
        client.delete(
            collection_name=collection_name,
            points_selector=qmodels.PointIdsList(points=point_ids),
            wait=True,
        )
        return len(point_ids)

    def count(self, collection_name: str) -> int:
        """Return total chunks in collection."""
        client = self._ensure_connected()
        if not self.collection_exists(collection_name):
            return 0
        res = client.count(collection_name=collection_name, exact=True)
        return res.count

    def delete_collection(self, collection_name: str) -> bool:
        """Drop collection entirely."""
        client = self._ensure_connected()
        if self.collection_exists(collection_name):
            return client.delete_collection(collection_name=collection_name)
        return False
