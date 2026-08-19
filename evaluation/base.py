"""
Engineering Intelligence Hub — Abstract Evaluator Interface
============================================================
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import List

from evaluation.metrics import ExperimentResult, QualityMetrics


class BaseEvaluator(ABC):
    """
    Abstract interface for evaluation pipelines.

    An evaluator takes a completed ExperimentResult and computes
    QualityMetrics, populating missing fields.

    Phase-1 implementations:
      - CorrectnessEvaluator  : compares against benchmark ground truth
      - GroundednessEvaluator : LLM-as-judge groundedness
      - RelevanceEvaluator    : LLM-as-judge relevance
      - CodeEvaluator         : compilation + test execution
    """

    @property
    @abstractmethod
    def evaluator_name(self) -> str:
        ...

    @abstractmethod
    def evaluate(self, result: ExperimentResult) -> QualityMetrics:
        """
        Compute quality metrics for a completed experiment result.

        Parameters
        ----------
        result : ExperimentResult
            Must have answer_text populated.

        Returns
        -------
        QualityMetrics
            May partially overlap with result.quality if already partially
            filled. Caller merges.
        """
        ...

    def evaluate_batch(self, results: List[ExperimentResult]) -> List[QualityMetrics]:
        """
        Evaluate a batch of results.
        Default implementation calls evaluate() sequentially.
        Override for batched LLM-as-judge calls (more efficient).
        """
        return [self.evaluate(r) for r in results]
