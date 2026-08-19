"""
Engineering Intelligence Hub — Quality Gate with Escalation Logic
=================================================================
Implements the core PASS / ESCALATE / FAIL decision loop.

The quality gate:
1. Runs all applicable evaluators on the current response.
2. If quality >= threshold → PASS, return response.
3. If quality < threshold and escalations remain → ESCALATE.
   (Escalation = try stronger retrieval / stronger model — handled by caller.)
4. If escalations exhausted → FAIL (raise EscalationExhaustedError).

This module contains only the gate logic — escalation strategy
(which model/retrieval to upgrade to) is decided by the orchestrator.

Principle: The system must NEVER intentionally return a low-quality
response merely to save resources. Escalation is mandatory on failure.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

from core.exceptions import EscalationExhaustedError, QualityGateError
from core.logging import get_logger
from knowledge.schemas.tasks import EngTaskRequest, EngTaskResponse
from verification.base import BaseQualityEvaluator
from verification.signals import QualityReport, QualitySignal, SignalStatus

logger = get_logger(__name__)


@dataclass
class EscalationRecord:
    """Records the outcome of one escalation attempt."""

    attempt_number: int
    quality_report: QualityReport
    escalation_reason: str
    escalated_model_id: Optional[str] = None
    escalated_strategy_name: Optional[str] = None


@dataclass
class QualityGateResult:
    """Final result produced by QualityGate.evaluate()."""

    passed: bool
    final_report: QualityReport
    escalation_history: List[EscalationRecord] = field(default_factory=list)
    total_escalations: int = 0
    gate_error: Optional[str] = None


class QualityGate:
    """
    Quality gate with configurable evaluators and escalation support.

    Usage example
    -------------
    gate = QualityGate(
        evaluators=[relevance_eval, groundedness_eval],
        max_escalations=2,
    )

    # First attempt
    result = gate.check(request, response, threshold=0.75)
    if not result.passed:
        # Orchestrator escalates (stronger model/retrieval) then:
        result = gate.check(request, improved_response, threshold=0.75, attempt=1)
    """

    def __init__(
        self,
        evaluators: Optional[List[BaseQualityEvaluator]] = None,
        max_escalations: int = 2,
    ) -> None:
        self.evaluators: List[BaseQualityEvaluator] = evaluators or []
        self.max_escalations = max_escalations

    def add_evaluator(self, evaluator: BaseQualityEvaluator) -> None:
        """Register an additional evaluator."""
        self.evaluators.append(evaluator)

    def check(
        self,
        request: EngTaskRequest,
        response: EngTaskResponse,
        threshold: float,
        attempt: int = 0,
    ) -> QualityReport:
        """
        Run all applicable evaluators and return a QualityReport.

        Parameters
        ----------
        request : EngTaskRequest
        response : EngTaskResponse
        threshold : float
            Minimum acceptable quality score.
        attempt : int
            Current attempt number (0 = first try, 1+ = escalations).

        Returns
        -------
        QualityReport
            Contains aggregated score, pass/fail, and per-signal breakdown.

        Raises
        ------
        EscalationExhaustedError
            If attempt >= max_escalations and quality still fails.
        QualityGateError
            If the gate itself encounters an unexpected error.
        """
        all_signals: List[QualitySignal] = []

        if not self.evaluators:
            # No evaluators registered — warn and pass through.
            logger.warning(
                f"QualityGate has no evaluators registered for task_id={request.task_id}. "
                "Treating as PASS. Register evaluators before production use."
            )
            return QualityReport(
                task_id=request.task_id,
                model_id=response.model_id,
                signals=[],
                aggregated_score=None,
                threshold_applied=threshold,
                passed=True,
            )

        for evaluator in self.evaluators:
            try:
                if not evaluator.is_applicable(request):
                    logger.debug(
                        f"Evaluator '{evaluator.evaluator_name}' skipped "
                        f"(not applicable to task_type={request.metadata.get('task_type', 'unknown')})"
                    )
                    continue
                signals = evaluator.evaluate(request, response)
                all_signals.extend(signals)
            except Exception as exc:  # noqa: BLE001
                logger.error(
                    f"Evaluator '{evaluator.evaluator_name}' raised unexpected error: {exc}"
                )
                # Add an error signal so the report reflects the failure.
                from verification.signals import SignalType
                all_signals.append(
                    QualitySignal(
                        signal_type=SignalType.CUSTOM,
                        status=SignalStatus.ERROR,
                        rationale=f"Evaluator error: {exc}",
                        evaluator_name=evaluator.evaluator_name,
                    )
                )

        report = QualityReport.compute(
            task_id=request.task_id,
            signals=all_signals,
            threshold=threshold,
            model_id=response.model_id,
        )

        logger.info(
            f"QualityGate attempt={attempt} task_id={request.task_id} "
            f"score={report.aggregated_score} threshold={threshold} "
            f"passed={report.passed}"
        )

        if not report.passed and attempt >= self.max_escalations:
            raise EscalationExhaustedError(
                message=(
                    f"Quality gate failed after {attempt} escalation(s). "
                    f"Best score: {report.aggregated_score}, required: {threshold}"
                ),
                details=f"Critical failures: {report.critical_failures}",
            )

        return report
