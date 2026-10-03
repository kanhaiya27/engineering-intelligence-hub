"""
Engineering Intelligence Hub — Baseline Evaluator Suite
========================================================
Combines correctness, groundedness, and relevance evaluators into a unified evaluation pass.
"""

from __future__ import annotations

from typing import List, Optional

from evaluation.base import BaseEvaluator
from evaluation.metrics import ExperimentResult, QualityMetrics
from evaluation.scorers.correctness import CorrectnessEvaluator
from evaluation.scorers.groundedness import GroundednessEvaluator
from evaluation.scorers.relevance import RelevanceEvaluator


class BaselineEvaluatorSuite(BaseEvaluator):
    """
    Composite evaluator executing correctness, groundedness, and relevance evaluators.
    """

    def __init__(
        self,
        correctness_evaluator: Optional[CorrectnessEvaluator] = None,
        groundedness_evaluator: Optional[GroundednessEvaluator] = None,
        relevance_evaluator: Optional[RelevanceEvaluator] = None,
    ) -> None:
        self.correctness = correctness_evaluator or CorrectnessEvaluator()
        self.groundedness = groundedness_evaluator or GroundednessEvaluator()
        self.relevance = relevance_evaluator or RelevanceEvaluator()

    @property
    def evaluator_name(self) -> str:
        return "baseline_evaluator_suite"

    def evaluate(
        self,
        result: ExperimentResult,
        query: Optional[str] = None,
        ground_truth: Optional[str] = None,
        acceptable_alternatives: Optional[List[str]] = None,
        context_chunks_text: Optional[str] = None,
    ) -> QualityMetrics:
        c_metrics = self.correctness.evaluate(
            result,
            ground_truth=ground_truth,
            acceptable_alternatives=acceptable_alternatives,
        )
        g_metrics = self.groundedness.evaluate(
            result,
            context_chunks_text=context_chunks_text,
        )
        r_metrics = self.relevance.evaluate(
            result,
            query=query,
        )

        scores = [
            c_metrics.task_correctness or 0.0,
            g_metrics.groundedness or 0.0,
            r_metrics.relevance or 0.0,
        ]
        agg_score = sum(scores) / len(scores)

        threshold = result.quality_threshold or 0.75
        passed = agg_score >= threshold

        return QualityMetrics(
            task_id=result.task_id,
            task_correctness=c_metrics.task_correctness,
            groundedness=g_metrics.groundedness,
            relevance=r_metrics.relevance,
            aggregated_quality_score=round(agg_score, 4),
            quality_threshold=threshold,
            passed_quality_gate=passed,
        )
