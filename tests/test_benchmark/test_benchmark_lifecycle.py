"""
Tests for Benchmark Lifecycle, Validator, and Dataset Manager
"""

from pathlib import Path
import pytest

from benchmark.dataset import BenchmarkDataset
from benchmark.validator import BenchmarkValidator
from core.config import PROJECT_ROOT
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


def test_load_and_validate_all_phase1_benchmark_tasks():
    benchmark_file = PROJECT_ROOT / "benchmark" / "data" / "meib_phase1_tasks.json"
    assert benchmark_file.exists()

    dataset = BenchmarkDataset.load_from_json(benchmark_file)
    assert len(dataset.tasks) == 60

    stats = dataset.get_statistics()
    assert stats["total_tasks"] == 60

    # Verify all 6 SDLC stages have exactly 10 tasks each
    for stage in [
        SDLCStage.REQUIREMENTS,
        SDLCStage.ARCHITECTURE,
        SDLCStage.DEVELOPMENT,
        SDLCStage.TESTING,
        SDLCStage.CODE_REVIEW,
        SDLCStage.MAINTENANCE,
    ]:
        stage_tasks = dataset.filter(sdlc_stage=stage)
        assert len(stage_tasks) == 10, f"Stage {stage} should have 10 tasks, found {len(stage_tasks)}"

    # Validate every task passes quality validation
    validator = BenchmarkValidator()
    results = validator.validate_batch(dataset.tasks)
    assert all(results), "All 60 benchmark tasks must pass automated validation."


def test_benchmark_task_promotion_lifecycle():
    validator = BenchmarkValidator()

    # Candidate task with valid evidence
    task = BenchmarkTask(
        task_id="test-candidate-1",
        repository="pallets/flask",
        sdlc_stage=SDLCStage.DEVELOPMENT,
        task_type=TaskType.CODE_GENERATION,
        difficulty=DifficultyLevel.EASY,
        complexity=ComplexityLevel.LOW,
        criticality=CriticalityLevel.LOW,
        query="How to create Flask application?",
        ground_truth="app = Flask(__name__)",
        expected_quality_threshold=0.8,
        source_evidence=[
            SourceEvidence(
                evidence_type=SourceEvidenceType.DOCUMENTATION,
                repository="pallets/flask",
                file_path="docs/quickstart.rst",
            )
        ],
        status=BenchmarkTaskStatus.CANDIDATE,
    )

    assert task.status == BenchmarkTaskStatus.CANDIDATE
    assert validator.validate(task) is True

    # Promote to approved
    approved = validator.promote_to_approved(task, reviewer_name="lead_researcher")
    assert approved.status == BenchmarkTaskStatus.APPROVED
    assert approved.human_approved_by == "lead_researcher"
    assert validator.validate(approved) is True
