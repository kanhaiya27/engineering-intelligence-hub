"""
Engineering Intelligence Hub — Rule-Based Task Classifier
==========================================================
Analyzes EngTaskRequest to identify SDLC stage, task type, complexity,
criticality, security sensitivity, and minimum required quality threshold.
"""

from __future__ import annotations

from typing import List, Optional, Tuple

from core.logging import get_logger
from intelligence.base import BaseTaskClassifier
from intelligence.complexity import HeuristicComplexityAnalyzer
from intelligence.criticality import HeuristicCriticalityAnalyzer
from knowledge.schemas.tasks import (
    EngTaskRequest,
    SDLCStage,
    TaskClassification,
    TaskType,
)

logger = get_logger(__name__)

# Keyword patterns mapping to (SDLCStage, TaskType)
_TASK_TYPE_RULES: List[Tuple[List[str], SDLCStage, TaskType]] = [
    # Testing
    (["test generation", "write a test", "write unit test", "pytest test", "test case"], SDLCStage.TESTING, TaskType.TEST_GENERATION),
    (["test failure", "test failing", "assertionerror", "test error", "pytest failed"], SDLCStage.TESTING, TaskType.TEST_FAILURE_ANALYSIS),
    (["explain test", "test purpose", "how to test", "testing strategy"], SDLCStage.TESTING, TaskType.TEST_EXPLANATION),

    # Code Review & Defect Detection
    (["defect", "vulnerability", "security review", "path traversal", "ssti", "review this snippet", "identify the defect", "cwe-"], SDLCStage.CODE_REVIEW, TaskType.DEFECT_DETECTION),
    (["risk", "concurrency bug", "race condition", "security risk", "privacy defect"], SDLCStage.CODE_REVIEW, TaskType.RISK_IDENTIFICATION),
    (["code review", "review this", "improve typing", "best practice review"], SDLCStage.CODE_REVIEW, TaskType.REVIEW_ASSISTANCE),

    # Maintenance & Operations
    (["diagnose", "traceback", "runtimeerror", "exception", "error", "stack trace", "why does uvicorn", "why does flask crash"], SDLCStage.OPERATIONS, TaskType.ERROR_ANALYSIS),
    (["root cause", "connection leak", "memory leak", "why does a database connection leak", "why does a reverse proxy"], SDLCStage.OPERATIONS, TaskType.ROOT_CAUSE_ASSISTANCE),
    (["what changed in", "deprecated", "deprecation", "removed in", "migration from", "compat"], SDLCStage.MAINTENANCE, TaskType.CHANGE_UNDERSTANDING),
    (["incident", "postmortem", "outage", "production incident"], SDLCStage.OPERATIONS, TaskType.INCIDENT_RETRIEVAL),

    # Architecture
    (["architecture", "architectural", "blueprint registration", "under the hood", "wsgi protocol", "asgi protocol", "how does starlette integrate", "design principle"], SDLCStage.ARCHITECTURE, TaskType.ARCHITECTURE_QA),
    (["dependency injection", "depends", "solve_dependencies", "dependency cycle", "sub-dependant"], SDLCStage.ARCHITECTURE, TaskType.DEPENDENCY_UNDERSTANDING),
    (["architecture decision", "adr", "trade-off between frameworks"], SDLCStage.ARCHITECTURE, TaskType.ARCHITECTURE_DECISION_SUPPORT),

    # Requirements
    (["requirement", "requirements for", "what configuration key", "openapi documentation generation", "session cookie security requirements", "oauth2 password flow"], SDLCStage.REQUIREMENTS, TaskType.REQUIREMENT_UNDERSTANDING),
    (["config key", "configuration parameter", "retrieval of requirement"], SDLCStage.REQUIREMENTS, TaskType.REQUIREMENT_RETRIEVAL),

    # Development / Code Generation & Explanation
    (["write a minimal", "write a custom", "write an endpoint", "write a flask", "write a fastapi", "implement a", "create an app", "template filter", "lifespan"], SDLCStage.DEVELOPMENT, TaskType.CODE_GENERATION),
    (["explain how", "how does", "how is", "what does", "requestcontext", "push() and pop()", "url_for", "flash()"], SDLCStage.DEVELOPMENT, TaskType.CODE_EXPLANATION),
    (["help with repository", "how to use", "repository assistance"], SDLCStage.DEVELOPMENT, TaskType.REPOSITORY_ASSISTANCE),
]


class RuleBasedTaskClassifier(BaseTaskClassifier):
    """
    Transparent rule-based task classifier for Phase-2 Task Intelligence.
    """

    def __init__(
        self,
        complexity_analyzer: Optional[HeuristicComplexityAnalyzer] = None,
        criticality_analyzer: Optional[HeuristicCriticalityAnalyzer] = None,
    ) -> None:
        self.complexity_analyzer = complexity_analyzer or HeuristicComplexityAnalyzer()
        self.criticality_analyzer = criticality_analyzer or HeuristicCriticalityAnalyzer()

    @property
    def classifier_name(self) -> str:
        return "rule_based_task_classifier"

    def _match_task_type(self, query: str) -> Tuple[SDLCStage, TaskType, float]:
        """Match query string against rule patterns to find SDLCStage and TaskType."""
        query_lower = query.lower()

        for keywords, stage, task_type in _TASK_TYPE_RULES:
            for kw in keywords:
                if kw in query_lower:
                    return stage, task_type, 0.90

        # Fallback default
        if "?" in query or query_lower.startswith(("what", "how", "why", "where")):
            return SDLCStage.DEVELOPMENT, TaskType.CODE_EXPLANATION, 0.70

        return SDLCStage.DEVELOPMENT, TaskType.REPOSITORY_ASSISTANCE, 0.60

    def classify(self, request: EngTaskRequest) -> TaskClassification:
        """
        Classify an incoming engineering task request.
        """
        reasons: List[str] = []

        # 1. Determine SDLCStage and TaskType (honoring hints if provided)
        matched_stage, matched_type, confidence = self._match_task_type(request.query)

        if request.sdlc_stage_hint and request.sdlc_stage_hint != SDLCStage.UNKNOWN:
            sdlc_stage = request.sdlc_stage_hint
            reasons.append(f"SDLC stage derived from user hint: {sdlc_stage}")
        else:
            sdlc_stage = matched_stage
            reasons.append(f"SDLC stage classified via rule matching: {sdlc_stage}")

        if request.task_type_hint and request.task_type_hint != TaskType.UNKNOWN:
            task_type = request.task_type_hint
            reasons.append(f"Task type derived from user hint: {task_type}")
        else:
            task_type = matched_type
            reasons.append(f"Task type classified via rule matching: {task_type}")

        # 2. Analyze complexity
        complexity, comp_score, comp_reasons = self.complexity_analyzer.analyze(
            query=request.query,
            sdlc_stage=sdlc_stage,
            task_type=task_type,
            context_files_count=len(request.context_files),
        )
        reasons.extend(comp_reasons)

        # 3. Analyze criticality, security sensitivity, and base quality threshold
        criticality, sec_sensitivity, base_threshold, crit_reasons = self.criticality_analyzer.analyze(
            query=request.query,
            sdlc_stage=sdlc_stage,
            task_type=task_type,
        )
        reasons.extend(crit_reasons)

        # 4. Determine final quality threshold (honoring override if provided)
        if request.quality_threshold_override is not None:
            quality_threshold = request.quality_threshold_override
            reasons.append(f"Quality threshold explicitly overridden: {quality_threshold}")
        else:
            quality_threshold = base_threshold

        reasoning_text = "; ".join(reasons)

        classification = TaskClassification(
            task_id=request.task_id,
            sdlc_stage=sdlc_stage,
            task_type=task_type,
            complexity=complexity,
            criticality=criticality,
            security_sensitivity=sec_sensitivity,
            quality_threshold=quality_threshold,
            classifier_confidence=confidence,
            reasoning=reasoning_text,
        )

        logger.debug(
            f"Classified task '{request.task_id}': stage={sdlc_stage}, "
            f"type={task_type}, complexity={complexity}, "
            f"criticality={criticality}, threshold={quality_threshold}"
        )

        return classification
