"""
Engineering Intelligence Hub — Groundedness Evaluator
=====================================================
Scores the extent to which a generated engineering answer is supported by the
retrieved context and contains verifiable source citations.
"""

from __future__ import annotations

import re
from typing import List, Optional

from core.logging import get_logger
from evaluation.base import BaseEvaluator
from evaluation.metrics import ExperimentResult, QualityMetrics

logger = get_logger(__name__)


class GroundednessEvaluator(BaseEvaluator):
    """
    Evaluates evidence grounding and citation compliance.
    """

    @property
    def evaluator_name(self) -> str:
        return "groundedness_evaluator"

    def evaluate(
        self,
        result: ExperimentResult,
        context_chunks_text: Optional[str] = None,
    ) -> QualityMetrics:
        text = result.answer_text or ""
        score = 0.5  # Baseline neutral

        # 1. Explicit grounding flag check
        if "SUPPORTED BY EVIDENCE" in text:
            score = 0.85
        elif "INSUFFICIENT EVIDENCE" in text:
            score = 0.90  # Correctly refused to hallucinate

        # 2. Citation detection (e.g. [src/app.py:L10], `flask/app.py`, line numbers)
        has_file_citation = bool(re.search(r"(\w+[\/]\w+\.\w+|\[.+:\w+\])", text))
        if has_file_citation:
            score = min(1.0, score + 0.15)

        # 3. Context overlap if provided
        if context_chunks_text:
            text_tokens = set(re.sub(r"[^\w\s]", " ", text.lower()).split())
            ctx_tokens = set(re.sub(r"[^\w\s]", " ", context_chunks_text.lower()).split())
            if ctx_tokens:
                overlap = len(text_tokens.intersection(ctx_tokens)) / max(1, len(text_tokens))
                score = min(1.0, (score * 0.7) + (overlap * 0.3))

        threshold = result.quality_threshold or 0.75
        passed = score >= threshold

        return QualityMetrics(
            task_id=result.task_id,
            groundedness=round(score, 4),
            aggregated_quality_score=round(score, 4),
            quality_threshold=threshold,
            passed_quality_gate=passed,
        )
