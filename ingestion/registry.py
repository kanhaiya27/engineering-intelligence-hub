"""
Engineering Intelligence Hub — Ingestion Source Registry
=========================================================
Registry for creating and discovering ingestion sources.
"""

from __future__ import annotations

from typing import Any, Dict, Optional, Type

from ingestion.base import BaseIngestionSource
from ingestion.loaders.file_loader import FileIngestionSource
from ingestion.loaders.github_loader import GitHubRepositoryIngestionSource


class IngestionRegistry:
    """Registry of ingestion source factories."""

    _registry: Dict[str, Type[BaseIngestionSource]] = {
        "file": FileIngestionSource,
        "github": GitHubRepositoryIngestionSource,
    }

    @classmethod
    def register(cls, name: str, source_cls: Type[BaseIngestionSource]) -> None:
        cls._registry[name] = source_cls

    @classmethod
    def get(cls, name: str) -> Optional[Type[BaseIngestionSource]]:
        return cls._registry.get(name)

    @classmethod
    def create(cls, source_type: str, **kwargs: Any) -> BaseIngestionSource:
        source_cls = cls._registry.get(source_type)
        if not source_cls:
            raise ValueError(f"Unknown ingestion source type '{source_type}'. Available: {list(cls._registry.keys())}")
        return source_cls(**kwargs)
