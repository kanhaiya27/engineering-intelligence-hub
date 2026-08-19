"""
Engineering Intelligence Hub — Benchmark Task Schema
=====================================================
Defines the BenchmarkTask model used for the Master Engineering Intelligence
Benchmark (MEIB).

Each task is a self-contained evaluation unit with:
- A query / prompt
- A ground truth / reference answer
- Structured metadata for stratified analysis
- Source evidence linking back to a repository artifact

Human approval is REQUIRED before a task is promoted to the official benchmark.
Do not auto-generate benchmark tasks without human review of this flag.

Research context
----------------
The benchmark is designed for temporal train/validation/test separation
where possible: tasks derived from repository history before a cutoff date
form the training/validation set; tasks from after the cutoff form the
hidden test set.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, model_validator

from knowledge.schemas.tasks import (
    ComplexityLevel,
    CriticalityLevel,
    SDLCStage,
    SecuritySensitivity,
    TaskType,
)


class DifficultyLevel(str, Enum):
    EASY = "easy"
    MEDIUM = "medium"
    HARD = "hard"
    EXPERT = "expert"


class BenchmarkTaskStatus(str, Enum):
    CANDIDATE = "candidate"       # Generated, not yet reviewed
    UNDER_REVIEW = "under_review" # Human is reviewing
    APPROVED = "approved"         # Officially part of the benchmark
    REJECTED = "rejected"         # Failed quality review
    DEPRECATED = "deprecated"     # Previously approved but now retired


class SourceEvidenceType(str, Enum):
    """Type of artefact that provides ground truth evidence."""
    SOURCE_FILE = "source_file"
    COMMIT = "commit"
    ISSUE = "issue"
    PULL_REQUEST = "pull_request"
    TEST = "test"
    INCIDENT = "incident"
    DOCUMENTATION = "documentation"
    ARCHITECTURE_DECISION = "architecture_decision"
    MANUAL = "manual"


class SourceEvidence(BaseModel):
    """
    A pointer to the repository artefact(s) that support the ground truth.
    Multiple evidence items may be cited per task.
    """

    evidence_type: SourceEvidenceType
    artifact_id: Optional[str] = Field(
        default=None, description="ID of the artifact in the EIH knowledge store"
    )
    repository: str = Field(description="Source repository (owner/repo)")
    file_path: Optional[str] = Field(
        default=None,
        description="Relative file path in the repository, if applicable",
    )
    line_start: Optional[int] = Field(default=None)
    line_end: Optional[int] = Field(default=None)
    commit_sha: Optional[str] = Field(
        default=None, description="Commit at which this evidence is valid"
    )
    url: Optional[str] = Field(
        default=None, description="Direct URL to the artefact (GitHub, GitLab, etc.)"
    )
    excerpt: Optional[str] = Field(
        default=None,
        description="Verbatim excerpt from the evidence artefact supporting the answer",
    )

    class Config:
        use_enum_values = True


class QualitySignalRequirements(BaseModel):
    """
    Specifies which quality signals are mandatory for this benchmark task.
    Allows task-type-specific evaluation without a one-size-fits-all scorer.
    """

    require_groundedness_check: bool = Field(default=True)
    require_relevance_check: bool = Field(default=True)
    require_correctness_check: bool = Field(default=True)
    require_code_compilation: bool = Field(
        default=False,
        description="Relevant for CODE_GENERATION tasks",
    )
    require_test_execution: bool = Field(
        default=False,
        description="Relevant for TEST_GENERATION tasks",
    )
    require_security_check: bool = Field(
        default=False,
        description="Relevant for tasks with high security sensitivity",
    )
    custom_signals: List[str] = Field(
        default_factory=list,
        description="Names of additional custom evaluators to invoke",
    )


class BenchmarkTask(BaseModel):
    """
    A single evaluation task in the Master Engineering Intelligence Benchmark.

    IMPORTANT: Only tasks with status=APPROVED may be used in official
    experiment evaluation. Use status=CANDIDATE for development/debugging.
    """

    # --- Identity ---
    task_id: str = Field(
        description="Unique task identifier, e.g. 'eih-dev-001-flask-code-explain'"
    )
    version: str = Field(
        default="1.0", description="Schema version of this benchmark task"
    )

    # --- Source ---
    repository: str = Field(description="Source repository (owner/repo)")
    sdlc_stage: SDLCStage = Field(description="SDLC stage this task belongs to")
    task_type: TaskType = Field(description="Fine-grained task type")

    # --- Classification ---
    difficulty: DifficultyLevel = Field(description="Estimated task difficulty")
    complexity: ComplexityLevel = Field(description="Estimated task complexity")
    criticality: CriticalityLevel = Field(
        description="Operational criticality of a correct answer"
    )
    security_sensitivity: SecuritySensitivity = Field(
        default=SecuritySensitivity.NONE,
        description="Security relevance of this task",
    )

    # --- Query and ground truth ---
    query: str = Field(description="The exact question / prompt posed to the system")
    ground_truth: str = Field(
        description=(
            "Reference answer or expected output. "
            "MUST be derived from evidence, not fabricated."
        )
    )
    acceptable_alternatives: List[str] = Field(
        default_factory=list,
        description=(
            "Additional correct formulations of the ground truth, "
            "used in fuzzy-match evaluation"
        ),
    )

    # --- Quality requirements ---
    expected_quality_threshold: float = Field(
        description="Minimum acceptable quality score for this task (0.0–1.0)",
        ge=0.0,
        le=1.0,
    )
    quality_signal_requirements: QualitySignalRequirements = Field(
        default_factory=QualitySignalRequirements
    )

    # --- Evidence ---
    source_evidence: List[SourceEvidence] = Field(
        default_factory=list,
        description=(
            "One or more evidence items supporting the ground truth. "
            "Tasks must have at least one evidence item before approval."
        ),
    )

    # --- Benchmark management ---
    status: BenchmarkTaskStatus = Field(
        default=BenchmarkTaskStatus.CANDIDATE,
        description="Lifecycle status — only APPROVED tasks used in official evaluation",
    )
    human_approved_by: Optional[str] = Field(
        default=None,
        description="Name/ID of the human reviewer who approved this task",
    )
    human_approved_at: Optional[str] = Field(
        default=None, description="ISO-8601 timestamp of human approval"
    )
    created_at: Optional[str] = Field(
        default=None, description="ISO-8601 timestamp when task was created"
    )
    temporal_split: Optional[str] = Field(
        default=None,
        description="train | validation | test — set during benchmark assembly",
    )
    notes: Optional[str] = Field(
        default=None,
        description="Reviewer or generator notes (not part of the query)",
    )
    tags: List[str] = Field(
        default_factory=list,
        description="Free-form tags for filtering (e.g. 'concurrency', 'security', 'api')",
    )
    metadata: Dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def check_approved_has_evidence(self) -> "BenchmarkTask":
        """
        Reject APPROVED tasks that have no source evidence.
        CANDIDATE tasks may have empty evidence (pre-review).
        """
        if (
            self.status == BenchmarkTaskStatus.APPROVED
            and not self.source_evidence
        ):
            raise ValueError(
                "An APPROVED benchmark task must have at least one source_evidence item."
            )
        return self

    class Config:
        use_enum_values = True
