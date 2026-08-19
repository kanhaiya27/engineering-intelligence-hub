"""
Engineering Intelligence Hub — Verification & Quality Gate Module (Phase-2 M4)
==============================================================================
Provides quality signals, evaluators, quality gate decision logic, and bounded escalation.
"""

from verification.base import BaseQualityEvaluator
from verification.config import VerificationConfig
from verification.escalation import EscalationPolicy
from verification.evaluators import (
    CitationGroundingEvaluator,
    EvidenceConsistencyEvaluator,
    EvidenceCoverageEvaluator,
    QueryRelevanceEvaluator,
)
from verification.gate import EscalationRecord, QualityGate, QualityGateResult
from verification.signals import (
    QualityReport,
    QualitySignal,
    SignalStatus,
    SignalType,
)

__all__ = [
    "BaseQualityEvaluator",
    "VerificationConfig",
    "EscalationPolicy",
    "CitationGroundingEvaluator",
    "EvidenceCoverageEvaluator",
    "QueryRelevanceEvaluator",
    "EvidenceConsistencyEvaluator",
    "QualityGate",
    "EscalationRecord",
    "QualityGateResult",
    "QualityReport",
    "QualitySignal",
    "SignalStatus",
    "SignalType",
]
