"""
Engineering Intelligence Hub — Abstract Experiment Runner
=========================================================
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import List

from evaluation.metrics import ExperimentResult
from experiments.config import ExperimentConfig
from experiments.logger import ExperimentLogger


class BaseExperimentRunner(ABC):
    """
    Abstract interface for experiment runners.

    A runner orchestrates one experimental configuration:
    1. Load benchmark tasks (filtered by config).
    2. For each task: retrieve → generate → verify → log.
    3. Compute aggregate metrics at end.

    Phase-1 concrete runners (in experiments/):
      - BaselineARunner  : LLM only, no RAG
      - BaselineBRunner  : Fixed RAG + fixed model
      - AdaptiveRunner   : Full adaptive pipeline
    """

    def __init__(
        self,
        config: ExperimentConfig,
        exp_logger: ExperimentLogger,
    ) -> None:
        self.config = config
        self.exp_logger = exp_logger

    @property
    @abstractmethod
    def runner_name(self) -> str:
        """Human-readable runner name."""
        ...

    @abstractmethod
    def run(self) -> List[ExperimentResult]:
        """
        Execute the experiment and return all result records.

        Must log each result via self.exp_logger.log_result().
        Must log escalations via self.exp_logger.log_escalation().

        Returns
        -------
        List[ExperimentResult]
        """
        ...

    def setup(self) -> None:
        """
        Optional pre-run setup (e.g. warm-up connections, load models).
        Called before run(). Default: no-op.
        """

    def teardown(self) -> None:
        """
        Optional post-run teardown. Called after run(). Default: no-op.
        """
