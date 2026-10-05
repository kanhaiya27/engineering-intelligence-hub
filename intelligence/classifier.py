"""
Engineering Intelligence Hub — Rule-Based Task Classifier
==========================================================
Analyzes EngTaskRequest to identify SDLC stage, task type, complexity,
criticality, security sensitivity, and minimum required quality threshold.
"""

from __future__ import annotations

import re
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

# Rule revision 2026-10-06 (Step 2a, WORK_PLAN C25), written from the 24 DEV tasks only; the 12
# val tasks were the untouched check (experiments/results/classifier/). General changes only, no
# task-specific keywords:
#   * imperative requests ("write/implement/create ...") are generation tasks and are matched before
#     anything else, so "write an error handler" is not error analysis;
#   * errors raised in a test setting ("test suite", "pytest", "test client") are test-failure analysis;
#   * past-tense change questions ("how did X replace/update ...") are change understanding;
#   * error diagnosis and root-cause analysis are MAINTENANCE: the benchmark's six SDLC stages have
#     no "operations" (only incident retrieval stays OPERATIONS);
#   * explaining how an existing component works is ARCHITECTURE-stage code explanation;
#   * lookups of configuration keys / provided utilities are requirement retrieval;
#   * "what happens if ..." in a review is defect detection.

_GENERATION_START = re.compile(r"^\s*(please\s+)?(write|implement|create|build|add|generate)\b")
_TEST_WORD = re.compile(r"\b(test|tests|pytest|unittest|testclient|test_client)\b")
_TEST_SETTING = ("test suite", "test suites", "in tests", "pytest", "test client", "test_client", "testclient")
_ERROR_CUES = ("diagnose", "traceback", "runtimeerror", "exception", "error", "stack trace", "raise", "crash")

# Keyword patterns mapping to (SDLCStage, TaskType), checked in order after the rules above.
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
    (["what changed in", "deprecated", "deprecation", "removed in", "migration from", "compat", "how did"], SDLCStage.MAINTENANCE, TaskType.CHANGE_UNDERSTANDING),
    (["diagnose", "traceback", "runtimeerror", "exception", "error", "stack trace", "why does uvicorn", "why does flask crash"], SDLCStage.MAINTENANCE, TaskType.ERROR_ANALYSIS),
    (["root cause", "connection leak", "memory leak", "why does a database connection leak", "why does a reverse proxy"], SDLCStage.MAINTENANCE, TaskType.ROOT_CAUSE_ASSISTANCE),
    (["incident", "postmortem", "outage", "production incident"], SDLCStage.OPERATIONS, TaskType.INCIDENT_RETRIEVAL),

    # Architecture
    (["architecture", "architectural", "blueprint registration", "under the hood", "wsgi protocol", "asgi protocol", "how does starlette integrate", "design principle"], SDLCStage.ARCHITECTURE, TaskType.ARCHITECTURE_QA),
    (["dependency injection", "depends", "solve_dependencies", "dependency cycle", "sub-dependant"], SDLCStage.ARCHITECTURE, TaskType.DEPENDENCY_UNDERSTANDING),
    (["architecture decision", "adr", "trade-off between frameworks"], SDLCStage.ARCHITECTURE, TaskType.ARCHITECTURE_DECISION_SUPPORT),

    # Requirements
    (["what configuration key", "config key", "configuration parameter", "retrieval of requirement", "oauth2 password flow", "does fastapi provide", "does flask provide"], SDLCStage.REQUIREMENTS, TaskType.REQUIREMENT_RETRIEVAL),
    (["requirement", "requirements for", "openapi documentation generation", "session cookie security requirements"], SDLCStage.REQUIREMENTS, TaskType.REQUIREMENT_UNDERSTANDING),

    # Development / Code Generation & Explanation
    (["write a minimal", "write a custom", "write an endpoint", "write a flask", "write a fastapi", "implement a", "create an app", "template filter", "lifespan"], SDLCStage.DEVELOPMENT, TaskType.CODE_GENERATION),
    (["explain how", "how does", "how is", "what does", "requestcontext", "push() and pop()", "url_for", "flash()"], SDLCStage.ARCHITECTURE, TaskType.CODE_EXPLANATION),
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

        # 1. Imperative requests are generation tasks (before any error keyword).
        if _GENERATION_START.search(query_lower):
            if _TEST_WORD.search(query_lower):
                return SDLCStage.TESTING, TaskType.TEST_GENERATION, 0.90
            return SDLCStage.DEVELOPMENT, TaskType.CODE_GENERATION, 0.90

        # 2. An error raised in a test setting is test-failure analysis.
        if any(c in query_lower for c in _TEST_SETTING) and any(c in query_lower for c in _ERROR_CUES):
            return SDLCStage.TESTING, TaskType.TEST_FAILURE_ANALYSIS, 0.85

        # 3. "What happens if ..." in a review is defect detection.
        if "review" in query_lower and "what happens if" in query_lower:
            return SDLCStage.CODE_REVIEW, TaskType.DEFECT_DETECTION, 0.85

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
