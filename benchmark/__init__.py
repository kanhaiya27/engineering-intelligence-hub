"""
Engineering Intelligence Hub — Benchmark Pipeline Stubs
=======================================================
Phase-0: Interfaces only. Concrete implementations in Phase-1.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import List

from knowledge.schemas.benchmark import BenchmarkTask
from knowledge.schemas.tasks import EngTaskRequest


class BaseBenchmarkGenerator(ABC):
    """
    Abstract interface for benchmark task generation.

    Implementations extract candidate tasks from ingested knowledge.
    """

    @abstractmethod
    def generate_candidates(
        self,
        repository: str,
        max_tasks: int = 100,
    ) -> List[BenchmarkTask]:
        """Generate candidate benchmark tasks for a repository."""
        ...


class BaseBenchmarkValidator(ABC):
    """
    Abstract interface for benchmark task validation.

    Validates task quality before human review.
    """

    @abstractmethod
    def validate(self, task: BenchmarkTask) -> bool:
        """
        Return True if the task passes automated quality checks.
        - Query is non-trivial (not a one-word question)
        - Ground truth is non-empty
        - Source evidence is present (for APPROVED tasks)
        - Expected quality threshold is in valid range
        """
        ...

    @abstractmethod
    def validate_batch(self, tasks: List[BenchmarkTask]) -> List[bool]:
        """Validate a list of tasks. Returns a list of pass/fail booleans."""
        ...
