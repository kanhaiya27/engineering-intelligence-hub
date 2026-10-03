"""
Engineering Intelligence Hub — Benchmark Dataset Splitting Protocol (M5)
=========================================================================
Implements deterministic, stratified dataset partitioning for the 60-task benchmark:
  - Development Set (Dev): 24 tasks (40%) — used for heuristic tuning, retrieval weights, debugging
  - Validation Set (Val): 12 tasks (20%) — used for parameter selection & candidate comparison
  - Held-Out Test Set (Test): 24 tasks (40%) — FROZEN FOR FINAL EVALUATION ONLY

Stratification Criteria:
  - Exact balance across 6 SDLC stages (Requirements, Architecture, Development, Testing, Code Review, Maintenance)
  - Exact balance across 2 pinned repositories (pallets/flask, fastapi/fastapi)
  - Fixed random seed (seed = 42) ensures absolute reproducibility.

IMPORTANT RESEARCH NOTE:
N = 60 is a controlled engineering benchmark, not a large statistical corpus.
Held-out test set MUST NOT be used for tuning or rule authoring.
"""

from __future__ import annotations

import json
import random
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from core.logging import get_logger
from knowledge.schemas.benchmark import BenchmarkTask

logger = get_logger(__name__)

FROZEN_BENCHMARK_VERSION = "v1.0-phase1-60"
DEFAULT_SPLIT_SEED = 42

DEFAULT_SPLIT_PATH = Path("benchmark/data/splits_v1.0.json")
BENCHMARK_TASKS_PATH = Path("benchmark/data/meib_phase1_tasks.json")


def create_stratified_splits(
    tasks: List[BenchmarkTask],
    seed: int = DEFAULT_SPLIT_SEED,
    dev_ratio: float = 0.40,
    val_ratio: float = 0.20,
    test_ratio: float = 0.40,
) -> Dict[str, List[str]]:
    """
    Partition benchmark tasks into Dev, Val, and Held-Out Test splits
    using stratified sampling across (sdlc_stage, repository) pairs.

    Parameters
    ----------
    tasks : List[BenchmarkTask]
        List of all 60 benchmark tasks.
    seed : int
        Fixed random seed for deterministic shuffling.
    dev_ratio, val_ratio, test_ratio : float
        Split ratios summing to 1.0.

    Returns
    -------
    Dict[str, List[str]]
        Dictionary with keys 'dev', 'val', 'test' mapping to lists of task_ids.
    """
    if abs((dev_ratio + val_ratio + test_ratio) - 1.0) > 1e-6:
        raise ValueError("Split ratios must sum to 1.0")

    # Group tasks into strata: (sdlc_stage, repository)
    strata: Dict[Tuple[str, str], List[BenchmarkTask]] = {}
    for task in tasks:
        stage = task.sdlc_stage.value if hasattr(task.sdlc_stage, "value") else str(task.sdlc_stage)
        repo = task.repository
        key = (stage, repo)
        if key not in strata:
            strata[key] = []
        strata[key].append(task)

    rng = random.Random(seed)

    dev_ids: List[str] = []
    val_ids: List[str] = []
    test_ids: List[str] = []

    # For each stratum (each containing 5 tasks):
    # With seed=42 shuffle: assign 2 to dev, 1 to val, 2 to test.
    for (stage, repo), stratum_tasks in sorted(strata.items()):
        # Sort first for deterministic baseline before shuffle
        sorted_tasks = sorted(stratum_tasks, key=lambda t: t.task_id)
        shuffled = sorted_tasks.copy()
        rng.shuffle(shuffled)

        n = len(shuffled)
        if n == 5:
            # Standard 5-task stratum
            dev_ids.extend([t.task_id for t in shuffled[0:2]])   # 2 tasks (40%)
            val_ids.extend([t.task_id for t in shuffled[2:3]])   # 1 task (20%)
            test_ids.extend([t.task_id for t in shuffled[3:5]])  # 2 tasks (40%)
        else:
            # Generalized proportional split
            n_dev = max(1, round(n * dev_ratio))
            n_val = max(1, round(n * val_ratio))
            dev_ids.extend([t.task_id for t in shuffled[:n_dev]])
            val_ids.extend([t.task_id for t in shuffled[n_dev : n_dev + n_val]])
            test_ids.extend([t.task_id for t in shuffled[n_dev + n_val :]])

    logger.info(
        f"Generated stratified splits (seed={seed}): "
        f"Dev={len(dev_ids)}, Val={len(val_ids)}, Test={len(test_ids)}"
    )

    return {
        "benchmark_version": FROZEN_BENCHMARK_VERSION,
        "seed": seed,
        "total_tasks": len(tasks),
        "split_counts": {
            "dev": len(dev_ids),
            "val": len(val_ids),
            "test": len(test_ids),
        },
        "splits": {
            "dev": sorted(dev_ids),
            "val": sorted(val_ids),
            "test": sorted(test_ids),
        },
    }


def load_or_create_splits(
    splits_file: Optional[Path] = None,
    tasks_file: Optional[Path] = None,
    seed: int = DEFAULT_SPLIT_SEED,
) -> Dict[str, Any]:
    """
    Load existing splits JSON file or generate it from tasks.
    """
    s_path = splits_file or DEFAULT_SPLIT_PATH
    t_path = tasks_file or BENCHMARK_TASKS_PATH

    if s_path.exists():
        with open(s_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data

    # Generate and save splits
    with open(t_path, "r", encoding="utf-8") as f:
        raw = json.load(f)
    raw_tasks = raw.get("tasks", raw)
    tasks = [BenchmarkTask(**t) for t in raw_tasks]

    split_data = create_stratified_splits(tasks, seed=seed)

    s_path.parent.mkdir(parents=True, exist_ok=True)
    with open(s_path, "w", encoding="utf-8") as f:
        json.dump(split_data, f, indent=2)

    return split_data
