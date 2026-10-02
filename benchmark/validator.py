"""
Engineering Intelligence Hub — Benchmark Task Validator & Lifecycle Manager
============================================================================
Enforces quality gates and lifecycle rules (CANDIDATE → VALIDATED → APPROVED)
for the Master Engineering Intelligence Benchmark.
"""

from __future__ import annotations

from typing import List

from benchmark import BaseBenchmarkValidator
from core.exceptions import InvalidBenchmarkTaskError
from core.logging import get_logger
from knowledge.schemas.benchmark import BenchmarkTask, BenchmarkTaskStatus

logger = get_logger(__name__)


class BenchmarkValidator(BaseBenchmarkValidator):
    """
    Validates benchmark task quality and manages promotion lifecycle.
    """

    def validate(self, task: BenchmarkTask) -> bool:
        """
        Validate a single benchmark task against research quality criteria.
        """
        # 1. Query checks
        if not task.query or len(task.query.strip()) < 10:
            logger.warning(f"Task '{task.task_id}' failed validation: query too short (< 10 chars).")
            return False

        # 2. Ground truth checks
        if not task.ground_truth or len(task.ground_truth.strip()) < 10:
            logger.warning(f"Task '{task.task_id}' failed validation: ground_truth too short (< 10 chars).")
            return False

        # 3. Quality threshold range
        if not (0.0 <= task.expected_quality_threshold <= 1.0):
            logger.warning(f"Task '{task.task_id}' failed validation: expected_quality_threshold out of bounds.")
            return False

        # 4. Approved task evidence check
        if task.status == BenchmarkTaskStatus.APPROVED:
            if not task.source_evidence or len(task.source_evidence) == 0:
                logger.warning(f"Task '{task.task_id}' failed validation: APPROVED task must have source evidence.")
                return False

        return True

    def validate_batch(self, tasks: List[BenchmarkTask]) -> List[bool]:
        """Validate a list of tasks."""
        return [self.validate(t) for t in tasks]

    def promote_to_approved(
        self,
        task: BenchmarkTask,
        reviewer_name: str = "researcher",
    ) -> BenchmarkTask:
        """
        Promote a CANDIDATE or UNDER_REVIEW task to APPROVED after verification.
        """
        if not task.source_evidence:
            raise InvalidBenchmarkTaskError(
                f"Cannot promote task '{task.task_id}' to APPROVED without source evidence.",
                details="At least one SourceEvidence item is required.",
            )

        task.status = BenchmarkTaskStatus.APPROVED
        task.human_approved_by = reviewer_name
        return task
