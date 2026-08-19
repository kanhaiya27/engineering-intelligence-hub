"""
Engineering Intelligence Hub — Quality Signals
===============================================
Pydantic models for quality evaluation signals and the aggregated
quality report produced by the quality gate.

Design principle:
- Each QualitySignal is produced by one evaluator.
- Multiple signals are aggregated into a QualityReport.
- The QualityGate uses QualityReport to decide PASS / ESCALATE.
- All signals have a score in [0.0, 1.0] and a human-readable rationale.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class SignalType(str, Enum):
    """Type of quality signal."""
    CORRECTNESS = "correctness"
    RELEVANCE = "relevance"
    GROUNDEDNESS = "groundedness"
    CITATION_SUPPORT = "citation_support"
    CODE_COMPILATION = "code_compilation"
    TEST_EXECUTION = "test_execution"
    DIAGNOSIS_ACCURACY = "diagnosis_accuracy"
    SECURITY_CHECK = "security_check"
    COMPLETENESS = "completeness"
    CUSTOM = "custom"


class SignalStatus(str, Enum):
    PASSED = "passed"
    FAILED = "failed"
    SKIPPED = "skipped"   # Signal not applicable to this task type
    ERROR = "error"       # Evaluator encountered an internal error


class QualitySignal(BaseModel):
    """A single quality evaluation signal."""

    signal_type: SignalType
    status: SignalStatus
    score: Optional[float] = Field(
        default=None,
        description="Score in [0.0, 1.0]. None if the signal is pass/fail only.",
        ge=0.0,
        le=1.0,
    )
    weight: float = Field(
        default=1.0,
        description="Weight of this signal in the aggregated quality score",
        ge=0.0,
    )
    rationale: Optional[str] = Field(
        default=None,
        description="Human-readable explanation of the score/status",
    )
    evidence: Optional[str] = Field(
        default=None,
        description="Quoted evidence from retrieved context supporting the score",
    )
    evaluator_name: Optional[str] = Field(
        default=None,
        description="Name of the evaluator that produced this signal",
    )
    metadata: Dict[str, Any] = Field(default_factory=dict)

    class Config:
        use_enum_values = True


class QualityReport(BaseModel):
    """
    Aggregated quality report for a single generation output.

    The aggregated_score is the weighted average of all non-skipped,
    non-error signals that have a numeric score.
    """

    task_id: str
    model_id: Optional[str] = None
    signals: List[QualitySignal] = Field(default_factory=list)
    aggregated_score: Optional[float] = Field(
        default=None,
        description="Weighted average quality score (0.0–1.0). "
                    "None if no scoreable signals are present.",
        ge=0.0,
        le=1.0,
    )
    threshold_applied: float = Field(
        description="The quality threshold that was checked against"
    )
    passed: bool = Field(
        description="True if aggregated_score >= threshold_applied"
    )
    critical_failures: List[str] = Field(
        default_factory=list,
        description="Signal types that hard-failed (score=0 or status=FAILED), "
                    "regardless of weighted average",
    )
    evaluator_errors: List[str] = Field(
        default_factory=list,
        description="Signal types where the evaluator itself errored",
    )
    metadata: Dict[str, Any] = Field(default_factory=dict)

    @classmethod
    def compute(
        cls,
        task_id: str,
        signals: List[QualitySignal],
        threshold: float,
        model_id: Optional[str] = None,
    ) -> "QualityReport":
        """
        Factory method: build a QualityReport by aggregating signals.

        Parameters
        ----------
        task_id : str
        signals : List[QualitySignal]
        threshold : float
        model_id : str, optional
        """
        total_weight = 0.0
        weighted_sum = 0.0
        critical_failures = []
        evaluator_errors = []

        for sig in signals:
            if sig.status == SignalStatus.SKIPPED:
                continue
            if sig.status == SignalStatus.ERROR:
                evaluator_errors.append(sig.signal_type)
                continue
            if sig.score is not None:
                weighted_sum += sig.score * sig.weight
                total_weight += sig.weight
            if sig.status == SignalStatus.FAILED and sig.score == 0.0:
                critical_failures.append(sig.signal_type)

        aggregated = (weighted_sum / total_weight) if total_weight > 0 else None
        passed = (aggregated is not None and aggregated >= threshold) and not critical_failures

        return cls(
            task_id=task_id,
            model_id=model_id,
            signals=signals,
            aggregated_score=round(aggregated, 4) if aggregated is not None else None,
            threshold_applied=threshold,
            passed=passed,
            critical_failures=critical_failures,
            evaluator_errors=evaluator_errors,
        )
