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

from pydantic import BaseModel, ConfigDict, Field, model_validator

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

    model_config = ConfigDict(use_enum_values=True)


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

    model_config = ConfigDict(use_enum_values=True)


# ---------------------------------------------------------------------------
# Retrieval ground truth (EIH-SWE schema v2 "R" fields, dataset spec §5)
# ---------------------------------------------------------------------------
#
# Stored in a separate labels file (benchmark/data/retrieval_labels_v1.json),
# keyed by task_id, so adding labels never rewrites the frozen task file.


class RetrievalLabelStatus(str, Enum):
    DRAFT = "draft"        # resolved against the pinned source, awaiting human check
    VERIFIED = "verified"  # a named human reviewer confirmed every span
    FLAGGED = "flagged"    # no valid evidence exists in the corpus; see notes


class RequiredEvidence(BaseModel):
    """One span of the pinned repository that a correct answer depends on."""

    file: str = Field(description="Repo-relative POSIX path at the pinned commit")
    start_line: int = Field(ge=1)
    end_line: int = Field(ge=1)
    symbol: Optional[str] = Field(
        default=None, description="Qualified symbol or doc section heading"
    )
    why: str = Field(min_length=1, description="Why this span is needed")
    span_sha256: str = Field(
        description="sha256 of the span's text, so drift in the source is detectable"
    )
    chunk_ids: List[str] = Field(
        default_factory=list,
        description="Indexed chunks overlapping this span at label time",
    )

    @model_validator(mode="after")
    def _ordered(self) -> "RequiredEvidence":
        if self.end_line < self.start_line:
            raise ValueError("end_line must be >= start_line")
        if self.file.startswith("/") or "\\" in self.file or ".." in self.file.split("/"):
            raise ValueError("file must be a repo-relative POSIX path")
        return self


class RetrievalGroundTruth(BaseModel):
    """Retrieval labels for one task (relevant files, symbols and line spans)."""

    task_id: str
    split: str = Field(description="dev | val (test labels are created separately)")
    repository: str
    commit_sha: str = Field(pattern=r"^[0-9a-f]{40}$")
    relevant_files: List[str]
    alternative_files: List[str] = Field(
        default_factory=list,
        description="Near-identical variants (e.g. *_py310.py doc examples); "
        "retrieving one counts the same as its primary file",
    )
    relevant_symbols: List[str] = Field(default_factory=list)
    required_evidence: List[RequiredEvidence] = Field(default_factory=list)
    graph_paths: List[str] = Field(
        default_factory=list, description="Filled once the knowledge graph exists"
    )
    expected_citations: List[str] = Field(default_factory=list)
    label_status: RetrievalLabelStatus
    annotator: str
    verified_by: Optional[str] = None
    ground_truth_issue: Optional[str] = Field(
        default=None,
        description="Problem found in the task's existing ground_truth/evidence "
        "while labelling; the task file itself is not changed",
    )
    notes: Optional[str] = None

    @model_validator(mode="after")
    def _consistent(self) -> "RetrievalGroundTruth":
        if self.split == "test":
            raise ValueError("test-split labels are created under the blind protocol only")
        if self.label_status == RetrievalLabelStatus.FLAGGED:
            if not self.notes:
                raise ValueError("a flagged label must explain why in notes")
        elif not self.required_evidence:
            raise ValueError("draft/verified labels need at least one evidence span")
        if self.label_status == RetrievalLabelStatus.VERIFIED and not self.verified_by:
            raise ValueError("verified labels need verified_by")
        evidence_files = {e.file for e in self.required_evidence}
        if not evidence_files <= set(self.relevant_files):
            raise ValueError("every evidence file must be listed in relevant_files")
        return self

    model_config = ConfigDict(use_enum_values=True)


class RetrievalLabelSet(BaseModel):
    """The labels file: provenance header plus one entry per task."""

    labels_version: str
    benchmark_version: str
    created_at: str
    label_protocol: str
    repositories: Dict[str, str] = Field(description="repository -> pinned commit SHA")
    labels: List[RetrievalGroundTruth]
