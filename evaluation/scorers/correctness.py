"""
Engineering Intelligence Hub — Correctness Evaluator
=====================================================
Computes ground truth alignment and semantic correctness for engineering task answers.
"""

from __future__ import annotations

import re
from typing import List, Optional, Set

from core.logging import get_logger
from evaluation.base import BaseEvaluator
from evaluation.metrics import ExperimentResult, QualityMetrics

logger = get_logger(__name__)


def _normalize_tokens(text: str) -> Set[str]:
    """Extract normalized word tokens."""
    cleaned = re.sub(r"[^\w\s]", " ", text.lower())
    return set(cleaned.split())


class CorrectnessEvaluator(BaseEvaluator):
    """
    Evaluates response correctness by comparing generated text against ground truth.
    Uses token F1 overlap and acceptable alternative matching.
    """

    @property
    def evaluator_name(self) -> str:
        return "correctness_evaluator"

    def compute_f1_score(self, prediction: str, reference: str) -> float:
        """Compute token F1 overlap between prediction and reference."""
        pred_tokens = _normalize_tokens(prediction)
        ref_tokens = _normalize_tokens(reference)

        if not pred_tokens or not ref_tokens:
            return 0.0

        common = pred_tokens.intersection(ref_tokens)
        if not common:
            return 0.0

        precision = len(common) / len(pred_tokens)
        recall = len(common) / len(ref_tokens)
        f1 = (2 * precision * recall) / (precision + recall)
        return min(1.0, f1 * 1.5)  # Scale slightly for concise technical definitions

    def evaluate(
        self,
        result: ExperimentResult,
        ground_truth: Optional[str] = None,
        acceptable_alternatives: Optional[List[str]] = None,
    ) -> QualityMetrics:
        prediction = result.answer_text or ""
        ref = ground_truth if ground_truth is not None else (getattr(result, "ground_truth", "") or "")

        best_score = 0.0
        if ref:
            best_score = self.compute_f1_score(prediction, ref)

        if acceptable_alternatives:
            for alt in acceptable_alternatives:
                score = self.compute_f1_score(prediction, alt)
                if score > best_score:
                    best_score = score

        threshold = result.quality_threshold or 0.75
        passed = best_score >= threshold

        return QualityMetrics(
            task_id=result.task_id,
            task_correctness=round(best_score, 4),
            aggregated_quality_score=round(best_score, 4),
            quality_threshold=threshold,
            passed_quality_gate=passed,
        )
