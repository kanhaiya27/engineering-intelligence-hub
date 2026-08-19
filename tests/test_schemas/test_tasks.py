"""Tests for task schemas."""

from __future__ import annotations

import pytest

from knowledge.schemas.tasks import (
    ComplexityLevel,
    CriticalityLevel,
    EngTaskRequest,
    EngTaskResponse,
    RetrievalResult,
    RetrievedChunk,
    SDLCStage,
    SecuritySensitivity,
    TaskClassification,
    TaskStatus,
    TaskType,
)


class TestEngTaskRequest:
    def test_minimal_request(self):
        req = EngTaskRequest(
            task_id="task-001",
            query="Explain the authentication module",
        )
        assert req.task_id == "task-001"
        assert req.repository is None
        assert req.context_files == []
        assert req.quality_threshold_override is None

    def test_full_request(self):
        req = EngTaskRequest(
            task_id="task-002",
            query="Generate unit tests for the payment service",
            repository="acme/payment",
            sdlc_stage_hint=SDLCStage.TESTING,
            task_type_hint=TaskType.TEST_GENERATION,
            quality_threshold_override=0.85,
            experiment_id="exp-001",
        )
        assert req.sdlc_stage_hint == SDLCStage.TESTING
        assert req.quality_threshold_override == 0.85

    def test_quality_threshold_bounds(self):
        with pytest.raises(Exception):
            EngTaskRequest(task_id="t", query="q", quality_threshold_override=1.5)
        with pytest.raises(Exception):
            EngTaskRequest(task_id="t", query="q", quality_threshold_override=-0.1)


class TestTaskClassification:
    def test_basic_classification(self):
        cls = TaskClassification(
            task_id="task-001",
            sdlc_stage=SDLCStage.DEVELOPMENT,
            task_type=TaskType.CODE_EXPLANATION,
            complexity=ComplexityLevel.MEDIUM,
            criticality=CriticalityLevel.LOW,
            security_sensitivity=SecuritySensitivity.NONE,
            quality_threshold=0.75,
        )
        assert cls.quality_threshold == 0.75
        assert cls.classifier_confidence == 1.0

    def test_quality_threshold_bounds(self):
        with pytest.raises(Exception):
            TaskClassification(
                task_id="t",
                sdlc_stage=SDLCStage.TESTING,
                task_type=TaskType.TEST_GENERATION,
                complexity=ComplexityLevel.LOW,
                criticality=CriticalityLevel.LOW,
                security_sensitivity=SecuritySensitivity.NONE,
                quality_threshold=1.5,  # Invalid
            )


class TestEngTaskResponse:
    def test_minimal_response(self):
        resp = EngTaskResponse(
            task_id="task-001",
            answer="The authentication module uses JWT tokens.",
        )
        assert resp.status == TaskStatus.COMPLETED
        assert resp.escalation_count == 0
        assert resp.quality_score is None

    def test_response_with_sustainability(self):
        resp = EngTaskResponse(
            task_id="task-002",
            answer="Here are the unit tests...",
            model_id="gpt-4o-mini",
            input_tokens=500,
            output_tokens=300,
            latency_ms=1200.0,
            energy_joules=0.0023,
            cost_usd=0.00026,
            co2e_grams=0.000148,
            passed_quality_gate=True,
            quality_score=0.88,
        )
        assert resp.energy_joules == 0.0023
        assert resp.passed_quality_gate is True


class TestRetrievalResult:
    def test_retrieval_result(self):
        chunks = [
            RetrievedChunk(
                chunk_id="c-1",
                content="Authentication is handled via JWT.",
                score=0.92,
                repository="owner/repo",
                source_path="docs/auth.md",
            ),
            RetrievedChunk(
                chunk_id="c-2",
                content="Tokens expire after 3600 seconds.",
                score=0.85,
                repository="owner/repo",
                source_path="docs/auth.md",
            ),
        ]
        result = RetrievalResult(
            task_id="task-001",
            strategy_used="hybrid",
            chunks=chunks,
            total_retrieved=2,
            retrieval_latency_ms=45.2,
        )
        assert len(result.chunks) == 2
        assert result.chunks[0].score == 0.92
