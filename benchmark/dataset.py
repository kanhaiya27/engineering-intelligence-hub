"""
Engineering Intelligence Hub — Benchmark Dataset Management
=============================================================
Provides loading, filtering, validation, and analytics over the benchmark suite.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from benchmark.validator import BenchmarkValidator
from core.logging import get_logger
from knowledge.schemas.benchmark import BenchmarkTask, BenchmarkTaskStatus
from knowledge.schemas.tasks import SDLCStage, TaskType

logger = get_logger(__name__)


class BenchmarkDataset:
    """
    In-memory dataset of BenchmarkTasks with query and filtering utilities.
    """

    def __init__(self, tasks: Optional[List[BenchmarkTask]] = None) -> None:
        self.tasks: List[BenchmarkTask] = tasks or []
        self.validator = BenchmarkValidator()

    @classmethod
    def load_from_json(cls, file_path: str | Path) -> "BenchmarkDataset":
        """Load benchmark tasks from a JSON file."""
        p = Path(file_path)
        if not p.exists():
            raise FileNotFoundError(f"Benchmark file not found: {file_path}")

        with open(p, "r", encoding="utf-8") as f:
            raw_data = json.load(f)

        raw_tasks = raw_data.get("tasks", raw_data) if isinstance(raw_data, dict) else raw_data
        tasks = [BenchmarkTask(**t) for t in raw_tasks]
        logger.info(f"Loaded {len(tasks)} benchmark tasks from {file_path}")
        return cls(tasks=tasks)

    def save_to_json(self, file_path: str | Path) -> None:
        """Save benchmark tasks to a JSON file."""
        p = Path(file_path)
        p.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "version": "1.0",
            "task_count": len(self.tasks),
            "tasks": [t.model_dump() for t in self.tasks],
        }
        with open(p, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        logger.info(f"Saved {len(self.tasks)} benchmark tasks to {file_path}")

    def filter(
        self,
        repository: Optional[str] = None,
        sdlc_stage: Optional[SDLCStage] = None,
        task_type: Optional[TaskType] = None,
        status: Optional[BenchmarkTaskStatus] = None,
    ) -> List[BenchmarkTask]:
        """Filter tasks matching the specified criteria."""
        results = self.tasks
        if repository:
            results = [t for t in results if t.repository == repository]
        if sdlc_stage:
            results = [t for t in results if t.sdlc_stage == sdlc_stage]
        if task_type:
            results = [t for t in results if t.task_type == task_type]
        if status:
            results = [t for t in results if t.status == status]
        return results

    def get_statistics(self) -> Dict[str, Any]:
        """Compute distribution statistics over the benchmark dataset."""
        total = len(self.tasks)
        by_stage: Dict[str, int] = {}
        by_repo: Dict[str, int] = {}
        by_status: Dict[str, int] = {}
        by_difficulty: Dict[str, int] = {}

        for t in self.tasks:
            stage_str = t.sdlc_stage.value if hasattr(t.sdlc_stage, "value") else str(t.sdlc_stage)
            by_stage[stage_str] = by_stage.get(stage_str, 0) + 1

            by_repo[t.repository] = by_repo.get(t.repository, 0) + 1

            status_str = t.status.value if hasattr(t.status, "value") else str(t.status)
            by_status[status_str] = by_status.get(status_str, 0) + 1

            diff_str = t.difficulty.value if hasattr(t.difficulty, "value") else str(t.difficulty)
            by_difficulty[diff_str] = by_difficulty.get(diff_str, 0) + 1

        return {
            "total_tasks": total,
            "by_sdlc_stage": by_stage,
            "by_repository": by_repo,
            "by_status": by_status,
            "by_difficulty": by_difficulty,
        }
