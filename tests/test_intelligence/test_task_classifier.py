"""
Tests for RuleBasedTaskClassifier in intelligence/classifier.py
"""

import pytest

from intelligence.classifier import RuleBasedTaskClassifier
from knowledge.schemas.tasks import (
    ComplexityLevel,
    CriticalityLevel,
    EngTaskRequest,
    SDLCStage,
    SecuritySensitivity,
    TaskType,
)


@pytest.fixture
def classifier():
    return RuleBasedTaskClassifier()


def test_classify_architecture_question(classifier):
    req = EngTaskRequest(
        task_id="task-arch-1",
        query="Explain the architectural design principles of blueprint registration in Flask",
        repository="pallets/flask",
    )
    res = classifier.classify(req)

    assert res.task_id == "task-arch-1"
    assert res.sdlc_stage == SDLCStage.ARCHITECTURE
    assert res.task_type == TaskType.ARCHITECTURE_QA
    assert res.quality_threshold >= 0.75
    assert "architectural" in res.reasoning.lower()


def test_classify_code_generation_request(classifier):
    req = EngTaskRequest(
        task_id="task-dev-1",
        query="Write a minimal Flask application factory function create_app that initializes a Flask app",
        repository="pallets/flask",
    )
    res = classifier.classify(req)

    assert res.sdlc_stage == SDLCStage.DEVELOPMENT
    assert res.task_type == TaskType.CODE_GENERATION
    assert res.quality_threshold >= 0.75


def test_classify_test_generation_request(classifier):
    req = EngTaskRequest(
        task_id="task-test-1",
        query="Write a pytest test verifying that Flask test_client returns 200 OK for /health route",
        repository="pallets/flask",
    )
    res = classifier.classify(req)

    assert res.sdlc_stage == SDLCStage.TESTING
    assert res.task_type == TaskType.TEST_GENERATION


def test_classify_security_vulnerability_review(classifier):
    req = EngTaskRequest(
        task_id="task-sec-1",
        query="Review this snippet for path traversal and SSTI vulnerabilities: user_input = request.args.get('path')",
        repository="pallets/flask",
    )
    res = classifier.classify(req)

    assert res.sdlc_stage == SDLCStage.CODE_REVIEW
    assert res.task_type == TaskType.DEFECT_DETECTION
    assert res.security_sensitivity in {SecuritySensitivity.HIGH, SecuritySensitivity.MEDIUM}
    assert res.criticality in {CriticalityLevel.CRITICAL, CriticalityLevel.HIGH}
    assert res.quality_threshold >= 0.85


def test_classify_production_incident(classifier):
    req = EngTaskRequest(
        task_id="task-ops-1",
        query="Diagnose this production traceback: RuntimeError: Working outside of request context",
        repository="pallets/flask",
    )
    res = classifier.classify(req)

    assert res.sdlc_stage == SDLCStage.OPERATIONS
    assert res.task_type == TaskType.ERROR_ANALYSIS
    assert res.criticality in {CriticalityLevel.HIGH, CriticalityLevel.CRITICAL}


def test_classify_user_hints_and_threshold_override(classifier):
    req = EngTaskRequest(
        task_id="task-override-1",
        query="How to run Celery with Flask?",
        sdlc_stage_hint=SDLCStage.OPERATIONS,
        task_type_hint=TaskType.REPOSITORY_ASSISTANCE,
        quality_threshold_override=0.95,
    )
    res = classifier.classify(req)

    assert res.sdlc_stage == SDLCStage.OPERATIONS
    assert res.task_type == TaskType.REPOSITORY_ASSISTANCE
    assert res.quality_threshold == 0.95
    assert "overridden" in res.reasoning.lower()
