"""
Engineering Intelligence Hub — Relevance Evaluator
==================================================
Scores how directly a generated response addresses the user's engineering query.
"""

from __future__ import annotations

import re
from typing import Optional

from core.logging import get_logger
from evaluation.base import BaseEvaluator
from evaluation.metrics import ExperimentResult, QualityMetrics

logger = get_logger(__name__)


class RelevanceEvaluator(BaseEvaluator):
    """
    Evaluates response-to-query topical alignment.
    """

    @property
    def evaluator_name(self) -> str:
        return "relevance_evaluator"

    def evaluate(
        self,
        result: ExperimentResult,
        query: Optional[str] = None,
    ) -> QualityMetrics:
        prediction = (result.answer_text or "").lower()
        q = (query or "").lower()

        if not prediction or not q:
            score = 0.5
        else:
            q_words = [w for w in re.sub(r"[^\w\s]", " ", q).split() if len(w) > 2]
            if not q_words:
                score = 0.8
            else:
                matches = sum(1 for w in q_words if w in prediction)
                score = min(1.0, 0.4 + (matches / len(q_words)) * 0.6)

        threshold = result.quality_threshold or 0.75
        passed = score >= threshold

        return QualityMetrics(
            task_id=result.task_id,
            relevance=round(score, 4),
            aggregated_quality_score=round(score, 4),
            quality_threshold=threshold,
            passed_quality_gate=passed,
        )
