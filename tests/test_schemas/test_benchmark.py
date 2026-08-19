"""Tests for benchmark task schema."""

from __future__ import annotations

import pytest

from knowledge.schemas.benchmark import (
    BenchmarkTask,
    BenchmarkTaskStatus,
    DifficultyLevel,
    SourceEvidence,
    SourceEvidenceType,
)
from knowledge.schemas.tasks import (
    ComplexityLevel,
    CriticalityLevel,
    SDLCStage,
    SecuritySensitivity,
    TaskType,
)


def make_evidence(**kwargs) -> SourceEvidence:
    defaults = dict(
        evidence_type=SourceEvidenceType.SOURCE_FILE,
        repository="owner/repo",
        file_path="src/auth.py",
        excerpt="def authenticate(user, token): ...",
    )
    defaults.update(kwargs)
    return SourceEvidence(**defaults)


def make_task(**kwargs) -> BenchmarkTask:
    defaults = dict(
        task_id="eih-dev-001",
        repository="owner/repo",
        sdlc_stage=SDLCStage.DEVELOPMENT,
        task_type=TaskType.CODE_EXPLANATION,
        difficulty=DifficultyLevel.MEDIUM,
        complexity=ComplexityLevel.MEDIUM,
        criticality=CriticalityLevel.LOW,
        security_sensitivity=SecuritySensitivity.NONE,
        query="Explain the authenticate() function.",
        ground_truth="The authenticate() function validates a user token using JWT.",
        expected_quality_threshold=0.75,
        source_evidence=[make_evidence()],
    )
    defaults.update(kwargs)
    return BenchmarkTask(**defaults)


class TestBenchmarkTask:
    def test_candidate_task_created_successfully(self):
        task = make_task()
        assert task.status == BenchmarkTaskStatus.CANDIDATE
        assert task.human_approved_by is None

    def test_approved_task_requires_evidence(self):
        """APPROVED tasks without evidence should raise validation error."""
        with pytest.raises(Exception) as exc_info:
            BenchmarkTask(
                task_id="eih-dev-002",
                repository="owner/repo",
                sdlc_stage=SDLCStage.DEVELOPMENT,
                task_type=TaskType.CODE_EXPLANATION,
                difficulty=DifficultyLevel.EASY,
                complexity=ComplexityLevel.LOW,
                criticality=CriticalityLevel.LOW,
                security_sensitivity=SecuritySensitivity.NONE,
                query="Explain foo()",
                ground_truth="foo() does bar",
                expected_quality_threshold=0.75,
                source_evidence=[],  # Empty evidence
                status=BenchmarkTaskStatus.APPROVED,  # APPROVED → must have evidence
            )
        assert "evidence" in str(exc_info.value).lower()

    def test_candidate_task_without_evidence_is_allowed(self):
        """CANDIDATE tasks can have empty evidence (pre-review)."""
        task = make_task(source_evidence=[])
        assert task.status == BenchmarkTaskStatus.CANDIDATE
        assert task.source_evidence == []

    def test_task_metadata_fields(self):
        task = make_task(
            tags=["auth", "security"],
            notes="This is a reviewer note",
            temporal_split="train",
        )
        assert "auth" in task.tags
        assert task.temporal_split == "train"

    def test_task_serialisation_roundtrip(self):
        task = make_task()
        data = task.model_dump()
        restored = BenchmarkTask(**data)
        assert restored.task_id == task.task_id
        assert restored.expected_quality_threshold == task.expected_quality_threshold
        assert len(restored.source_evidence) == 1

    def test_quality_threshold_bounds(self):
        with pytest.raises(Exception):
            make_task(expected_quality_threshold=1.5)
        with pytest.raises(Exception):
            make_task(expected_quality_threshold=-0.1)


class TestSourceEvidence:
    def test_basic_evidence(self):
        ev = make_evidence()
        assert ev.evidence_type == SourceEvidenceType.SOURCE_FILE
        assert ev.repository == "owner/repo"

    def test_commit_evidence(self):
        ev = SourceEvidence(
            evidence_type=SourceEvidenceType.COMMIT,
            repository="owner/repo",
            commit_sha="abc123",
            url="https://github.com/owner/repo/commit/abc123",
            excerpt="Fixed memory leak in payment processor",
        )
        assert ev.commit_sha == "abc123"
