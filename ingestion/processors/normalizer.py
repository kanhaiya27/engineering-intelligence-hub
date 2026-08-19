"""
Engineering Intelligence Hub — Data Normalization & Processing Pipeline
========================================================================
Validates, normalizes, extracts metadata, deduplicates, and chunks raw engineering artifacts
into structured KnowledgeChunks ready for indexing.
"""

from __future__ import annotations

import hashlib
import re
from typing import Any, Dict, Iterator, List, Optional, Set

from core.logging import get_logger
from ingestion.processors.chunker import UniversalChunker
from knowledge.schemas.artifacts import BaseArtifact, KnowledgeChunk

logger = get_logger(__name__)


class ArtifactNormalizer:
    """
    Normalizes raw text content and metadata of BaseArtifacts.
    """

    def __init__(
        self,
        chunker: Optional[UniversalChunker] = None,
        deduplicate_content: bool = True,
    ) -> None:
        self.chunker = chunker or UniversalChunker()
        self.deduplicate_content = deduplicate_content
        self._seen_hashes: Set[str] = set()

    def normalize_text(self, text: Optional[str]) -> str:
        """Clean and normalize raw text."""
        if not text:
            return ""
        # Strip UTF-8 BOM
        if text.startswith("\ufeff"):
            text = text[1:]
        # Normalize line breaks to \n
        text = text.replace("\r\n", "\n").replace("\r", "\n")
        # Remove null bytes and non-printable control chars except \n, \t
        text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", text)
        return text

    def compute_content_hash(self, text: str) -> str:
        """Compute SHA-256 content hash."""
        return hashlib.sha256(text.encode("utf-8")).hexdigest()

    def process_artifact(self, artifact: BaseArtifact) -> List[KnowledgeChunk]:
        """
        Normalize a single artifact and produce its KnowledgeChunks.
        Returns empty list if invalid or duplicate.
        """
        if not artifact.raw_content:
            return []

        # 1. Normalize content
        normalized_content = self.normalize_text(artifact.raw_content)
        if not normalized_content.strip():
            return []

        # 2. Deduplicate
        content_hash = self.compute_content_hash(normalized_content)
        if self.deduplicate_content:
            if content_hash in self._seen_hashes:
                logger.debug(f"Skipping duplicate artifact content: {artifact.artifact_id}")
                return []
            self._seen_hashes.add(content_hash)

        # 3. Update artifact with normalized content & hash
        artifact.raw_content = normalized_content
        artifact.metadata["content_hash"] = content_hash
        artifact.metadata["char_count"] = len(normalized_content)
        artifact.metadata["line_count"] = len(normalized_content.splitlines())

        # 4. Chunk artifact
        chunks = self.chunker.chunk(artifact)

        # 5. Enrich chunks with provenance
        for chunk in chunks:
            chunk.metadata["content_hash"] = content_hash
            if "source_url" in artifact.metadata:
                chunk.metadata["source_url"] = artifact.metadata["source_url"]

        return chunks

    def process_stream(self, artifacts: Iterator[BaseArtifact]) -> Iterator[KnowledgeChunk]:
        """Process a stream of artifacts and yield KnowledgeChunks."""
        for artifact in artifacts:
            chunks = self.process_artifact(artifact)
            for chunk in chunks:
                yield chunk

    def reset_deduplication(self) -> None:
        """Clear the deduplication cache."""
        self._seen_hashes.clear()
