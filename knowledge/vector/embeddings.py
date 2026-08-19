"""
Engineering Intelligence Hub — Embedding Pipeline (BGE-Small-EN)
================================================================
Embeds text and KnowledgeChunks using BAAI/bge-small-en-v1.5 with PyTorch CUDA
acceleration on NVIDIA GeForce RTX 4050 GPU (with graceful CPU fallback).

Features:
- Batched inference for GPU efficiency.
- L2-normalized embeddings for fast cosine similarity via dot product.
- Memory and latency telemetry.
- Records model metadata, embedding dimension (384), and hardware device.
"""

from __future__ import annotations

import time
from typing import Any, Dict, List, Optional

import torch
from sentence_transformers import SentenceTransformer

from core.config import settings
from core.logging import get_logger
from knowledge.schemas.artifacts import KnowledgeChunk

logger = get_logger(__name__)


class BGEEmbeddingModel:
    """
    Embedding model wrapper for BAAI/bge-small-en-v1.5.
    """

    MODEL_ID = "BAAI/bge-small-en-v1.5"
    EMBEDDING_DIM = 384

    def __init__(
        self,
        model_name: Optional[str] = None,
        device: Optional[str] = None,
        batch_size: int = 32,
        normalize_embeddings: bool = True,
    ) -> None:
        self.model_name = model_name or settings.vector_store.embedding_model or self.MODEL_ID
        self.batch_size = batch_size
        self.normalize_embeddings = normalize_embeddings

        if device:
            self.device = device
        elif torch.cuda.is_available():
            self.device = "cuda:0"
        else:
            self.device = "cpu"

        logger.info(f"Loading embedding model '{self.model_name}' on device '{self.device}'...")
        self._model: Optional[SentenceTransformer] = None

    def _ensure_loaded(self) -> SentenceTransformer:
        """Lazy load the sentence transformer model."""
        if self._model is None:
            self._model = SentenceTransformer(self.model_name, device=self.device)
            logger.info(f"Loaded {self.model_name} on {self.device} (dim={self.EMBEDDING_DIM})")
        return self._model

    @property
    def embedding_dimension(self) -> int:
        return self.EMBEDDING_DIM

    @property
    def active_device(self) -> str:
        return self.device

    def embed_text(self, text: str) -> List[float]:
        """Embed a single query or text string."""
        model = self._ensure_loaded()
        vec = model.encode(
            text,
            normalize_embeddings=self.normalize_embeddings,
            convert_to_numpy=True,
            show_progress_bar=False,
        )
        return vec.tolist()

    def embed_batch(
        self,
        texts: List[str],
        batch_size: Optional[int] = None,
    ) -> List[List[float]]:
        """Embed a list of text strings in batches."""
        if not texts:
            return []
        model = self._ensure_loaded()
        bs = batch_size or self.batch_size
        embeddings = model.encode(
            texts,
            batch_size=bs,
            normalize_embeddings=self.normalize_embeddings,
            convert_to_numpy=True,
            show_progress_bar=False,
        )
        return embeddings.tolist()

    def embed_chunks(
        self,
        chunks: List[KnowledgeChunk],
        batch_size: Optional[int] = None,
    ) -> List[KnowledgeChunk]:
        """
        Embed a list of KnowledgeChunks and populate each chunk's .embedding field.
        """
        if not chunks:
            return chunks

        texts = [chunk.content for chunk in chunks]
        embeddings = self.embed_batch(texts, batch_size=batch_size)

        for chunk, emb in zip(chunks, embeddings):
            chunk.embedding = emb

        return chunks

    def benchmark(
        self,
        sample_texts: Optional[List[str]] = None,
        count: int = 64,
    ) -> Dict[str, Any]:
        """
        Benchmark embedding performance, throughput, latency, and peak memory.
        """
        if not sample_texts:
            sample_texts = [
                f"Defines HTTP request handler number {i} for endpoint /api/v1/resource with query parameter parsing."
                for i in range(count)
            ]

        model = self._ensure_loaded()

        if torch.cuda.is_available() and "cuda" in self.device:
            torch.cuda.reset_peak_memory_stats()
            torch.cuda.synchronize()

        start_time = time.perf_counter()
        embeddings = self.embed_batch(sample_texts)
        if torch.cuda.is_available() and "cuda" in self.device:
            torch.cuda.synchronize()
        elapsed_sec = time.perf_counter() - start_time

        peak_gpu_mb = 0.0
        if torch.cuda.is_available() and "cuda" in self.device:
            peak_gpu_mb = torch.cuda.max_memory_allocated() / (1024 * 1024)

        return {
            "model_name": self.model_name,
            "embedding_dim": self.EMBEDDING_DIM,
            "device": self.device,
            "item_count": len(sample_texts),
            "total_time_seconds": round(elapsed_sec, 4),
            "latency_per_item_ms": round((elapsed_sec / len(sample_texts)) * 1000, 2),
            "throughput_items_per_sec": round(len(sample_texts) / elapsed_sec, 2),
            "peak_gpu_memory_mb": round(peak_gpu_mb, 2),
        }
