"""
Engineering Intelligence Hub — Abstract Ingestion Interface
===========================================================
Defines the contract that every ingestion source loader must implement.

Extension guide
---------------
To add a new source type (e.g. Confluence, Jira, GitLab):
1. Create a class in ingestion/loaders/ that inherits from BaseIngestionSource.
2. Implement all abstract methods.
3. Register the loader in ingestion/registry.py (Phase-1).
4. Add a corresponding test in tests/test_ingestion/.

No external dependencies are imported here — the interface is pure Python.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import AsyncIterator, Iterator, List, Optional

from knowledge.schemas.artifacts import ArtifactType, BaseArtifact, KnowledgeChunk


class BaseIngestionSource(ABC):
    """
    Abstract base class for all ingestion source loaders.

    A loader is responsible for:
    1. Connecting to / reading from a data source.
    2. Yielding typed BaseArtifact instances.

    Chunking (splitting artifacts into KnowledgeChunks) is handled by
    ingestion/processors/chunker.py — not by the loader itself.
    """

    @property
    @abstractmethod
    def source_type(self) -> ArtifactType:
        """Return the ArtifactType this loader handles."""
        ...

    @property
    @abstractmethod
    def source_id(self) -> str:
        """A unique identifier for this source instance (e.g. 'github:owner/repo')."""
        ...

    @abstractmethod
    def validate_config(self) -> bool:
        """
        Validate that all required configuration is present and accessible.
        Returns True if valid, raises IngestionError otherwise.
        """
        ...

    @abstractmethod
    def load(self) -> Iterator[BaseArtifact]:
        """
        Synchronously load and yield artifacts from this source.

        Yields
        ------
        BaseArtifact
            One artifact per yield. The loader should NOT buffer all artifacts
            in memory — use a generator.
        """
        ...

    def load_async(self) -> AsyncIterator[BaseArtifact]:
        """
        Asynchronous variant of load().
        Default implementation wraps the synchronous load() — override for
        sources with native async APIs (e.g. GitHub REST API).
        """
        raise NotImplementedError(
            f"{self.__class__.__name__} does not implement load_async(). "
            "Override this method or use the synchronous load() instead."
        )

    def supports_incremental(self) -> bool:
        """
        Return True if this loader can perform incremental ingestion
        (i.e. only load artifacts modified after a given timestamp).
        Default: False.
        """
        return False

    def load_since(self, since_iso: str) -> Iterator[BaseArtifact]:
        """
        Load only artifacts updated after `since_iso` (ISO-8601 string).
        Only valid when supports_incremental() returns True.

        Raises
        ------
        NotImplementedError
            If the loader does not support incremental loading.
        """
        raise NotImplementedError(
            f"{self.__class__.__name__} does not support incremental loading."
        )

    def estimate_artifact_count(self) -> Optional[int]:
        """
        Estimate the total number of artifacts this source will yield.
        Return None if the count cannot be determined without full enumeration.
        """
        return None


class BaseChunker(ABC):
    """
    Abstract base class for text chunkers.

    Takes a BaseArtifact and produces a list of KnowledgeChunks.
    """

    @abstractmethod
    def chunk(self, artifact: BaseArtifact) -> List[KnowledgeChunk]:
        """
        Split an artifact's content into KnowledgeChunks.

        Parameters
        ----------
        artifact:
            A fully populated BaseArtifact with raw_content set.

        Returns
        -------
        List[KnowledgeChunk]
            Ordered list of chunks derived from the artifact.
        """
        ...

    @property
    @abstractmethod
    def chunker_name(self) -> str:
        """Human-readable name for logging and experiment tracking."""
        ...
