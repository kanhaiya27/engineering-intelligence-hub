"""
Engineering Intelligence Hub — Engineering Artifact Schemas
===========================================================
Pydantic models for every engineering artifact type that the system ingests
and represents in the knowledge store.

Design principles:
- All IDs are strings to remain provider-agnostic (UUID, SHA, slug, etc.).
- Timestamps are ISO-8601 strings so they survive JSON round-trips without
  timezone ambiguity issues in Python 3.8.
- Optional fields default to None — do not fabricate missing metadata.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field


# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------


class ArtifactType(str, Enum):
    """High-level category of an engineering artifact."""

    SOURCE_CODE = "source_code"
    MARKDOWN = "markdown"
    PLAIN_TEXT = "plain_text"
    PDF = "pdf"
    CONFIGURATION = "configuration"
    ISSUE = "issue"
    PULL_REQUEST = "pull_request"
    COMMIT = "commit"
    TEST = "test"
    INCIDENT = "incident"
    ARCHITECTURE_DECISION = "architecture_decision"
    API_DOCUMENTATION = "api_documentation"
    DEPENDENCY_MANIFEST = "dependency_manifest"
    UNKNOWN = "unknown"


class ProgrammingLanguage(str, Enum):
    PYTHON = "python"
    JAVASCRIPT = "javascript"
    TYPESCRIPT = "typescript"
    JAVA = "java"
    GO = "go"
    RUST = "rust"
    CPP = "cpp"
    C = "c"
    CSHARP = "csharp"
    RUBY = "ruby"
    KOTLIN = "kotlin"
    SCALA = "scala"
    SHELL = "shell"
    SQL = "sql"
    YAML = "yaml"
    JSON = "json"
    TOML = "toml"
    OTHER = "other"
    UNKNOWN = "unknown"


class IssueSeverity(str, Enum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    UNKNOWN = "unknown"


class IssueStatus(str, Enum):
    OPEN = "open"
    CLOSED = "closed"
    IN_PROGRESS = "in_progress"
    RESOLVED = "resolved"
    WONT_FIX = "wont_fix"
    UNKNOWN = "unknown"


# ---------------------------------------------------------------------------
# Base artifact
# ---------------------------------------------------------------------------


class BaseArtifact(BaseModel):
    """Common fields shared by all engineering artifacts."""

    artifact_id: str = Field(description="Unique artifact identifier")
    artifact_type: ArtifactType = Field(description="High-level artifact category")
    repository: str = Field(description="Repository name or URL (owner/repo)")
    source_path: Optional[str] = Field(
        default=None,
        description="Relative path within the repository, if applicable",
    )
    created_at: Optional[str] = Field(
        default=None, description="ISO-8601 creation timestamp"
    )
    updated_at: Optional[str] = Field(
        default=None, description="ISO-8601 last-updated timestamp"
    )
    raw_content: Optional[str] = Field(
        default=None, description="Raw text content of the artifact"
    )
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Arbitrary additional metadata for extension without schema changes",
    )

    model_config = ConfigDict(use_enum_values=True)


# ---------------------------------------------------------------------------
# Source file
# ---------------------------------------------------------------------------


class SourceFile(BaseArtifact):
    """A source code file ingested from a repository."""

    artifact_type: ArtifactType = ArtifactType.SOURCE_CODE
    language: ProgrammingLanguage = Field(
        default=ProgrammingLanguage.UNKNOWN,
        description="Detected programming language",
    )
    size_bytes: Optional[int] = Field(default=None, description="File size in bytes")
    line_count: Optional[int] = Field(default=None, description="Number of lines")
    is_test_file: bool = Field(
        default=False, description="True if this file is a test file"
    )
    imports: List[str] = Field(
        default_factory=list,
        description="List of detected imports/dependencies",
    )
    classes: List[str] = Field(
        default_factory=list, description="Top-level class names found in file"
    )
    functions: List[str] = Field(
        default_factory=list, description="Top-level function names found in file"
    )
    commit_sha: Optional[str] = Field(
        default=None, description="Git commit SHA at time of ingestion"
    )


# ---------------------------------------------------------------------------
# Commit
# ---------------------------------------------------------------------------


class Commit(BaseArtifact):
    """A Git commit record."""

    artifact_type: ArtifactType = ArtifactType.COMMIT
    sha: str = Field(description="Full commit SHA")
    author_name: Optional[str] = Field(default=None)
    author_email: Optional[str] = Field(default=None)
    committed_at: Optional[str] = Field(default=None, description="ISO-8601 timestamp")
    message: str = Field(description="Commit message")
    files_changed: List[str] = Field(
        default_factory=list, description="Relative paths of files modified"
    )
    insertions: Optional[int] = Field(default=None)
    deletions: Optional[int] = Field(default=None)
    branch: Optional[str] = Field(default=None)
    tags: List[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Issue
# ---------------------------------------------------------------------------


class Issue(BaseArtifact):
    """A GitHub/GitLab/Jira issue."""

    artifact_type: ArtifactType = ArtifactType.ISSUE
    issue_number: Optional[int] = Field(default=None)
    title: str = Field(description="Issue title")
    body: Optional[str] = Field(default=None, description="Issue description / body")
    author: Optional[str] = Field(default=None)
    assignees: List[str] = Field(default_factory=list)
    labels: List[str] = Field(default_factory=list)
    status: IssueStatus = Field(default=IssueStatus.UNKNOWN)
    severity: IssueSeverity = Field(default=IssueSeverity.UNKNOWN)
    closed_at: Optional[str] = Field(default=None)
    resolved_by_commit: Optional[str] = Field(
        default=None, description="SHA of commit that resolved this issue"
    )
    linked_pull_requests: List[str] = Field(
        default_factory=list, description="PR IDs linked to this issue"
    )


# ---------------------------------------------------------------------------
# Pull Request
# ---------------------------------------------------------------------------


class PullRequest(BaseArtifact):
    """A pull / merge request."""

    artifact_type: ArtifactType = ArtifactType.PULL_REQUEST
    pr_number: Optional[int] = Field(default=None)
    title: str = Field(description="PR title")
    body: Optional[str] = Field(default=None)
    author: Optional[str] = Field(default=None)
    reviewers: List[str] = Field(default_factory=list)
    labels: List[str] = Field(default_factory=list)
    base_branch: Optional[str] = Field(default=None)
    head_branch: Optional[str] = Field(default=None)
    merged_at: Optional[str] = Field(default=None)
    merge_commit_sha: Optional[str] = Field(default=None)
    files_changed: List[str] = Field(default_factory=list)
    linked_issues: List[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Test case
# ---------------------------------------------------------------------------


class TestCase(BaseArtifact):
    """A test file or individual test function."""

    artifact_type: ArtifactType = ArtifactType.TEST
    test_framework: Optional[str] = Field(
        default=None, description="e.g. pytest, JUnit, Jest"
    )
    test_names: List[str] = Field(
        default_factory=list, description="Individual test function/method names"
    )
    target_components: List[str] = Field(
        default_factory=list,
        description="Components or functions this test validates",
    )
    last_run_status: Optional[str] = Field(
        default=None, description="passed | failed | error | skipped"
    )
    last_run_at: Optional[str] = Field(default=None)


# ---------------------------------------------------------------------------
# Incident / postmortem
# ---------------------------------------------------------------------------


class IncidentReport(BaseArtifact):
    """An incident report or postmortem document."""

    artifact_type: ArtifactType = ArtifactType.INCIDENT
    incident_id: Optional[str] = Field(default=None)
    title: str = Field(description="Incident title or summary")
    severity: IssueSeverity = Field(default=IssueSeverity.UNKNOWN)
    affected_services: List[str] = Field(default_factory=list)
    root_cause: Optional[str] = Field(default=None)
    resolution: Optional[str] = Field(default=None)
    timeline: Optional[str] = Field(default=None)
    detected_at: Optional[str] = Field(default=None)
    resolved_at: Optional[str] = Field(default=None)
    linked_commits: List[str] = Field(default_factory=list)
    linked_issues: List[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Architecture decision record (ADR)
# ---------------------------------------------------------------------------


class ArchitectureDecision(BaseArtifact):
    """An Architecture Decision Record (ADR) or design document."""

    artifact_type: ArtifactType = ArtifactType.ARCHITECTURE_DECISION
    decision_id: Optional[str] = Field(default=None, description="e.g. ADR-0001")
    title: str = Field(description="Decision title")
    status: Optional[str] = Field(
        default=None,
        description="proposed | accepted | deprecated | superseded",
    )
    context: Optional[str] = Field(
        default=None, description="Problem context motivating this decision"
    )
    decision: Optional[str] = Field(
        default=None, description="The decision that was taken"
    )
    consequences: Optional[str] = Field(
        default=None, description="Expected consequences / trade-offs"
    )
    superseded_by: Optional[str] = Field(
        default=None, description="ID of the ADR that supersedes this one"
    )


# ---------------------------------------------------------------------------
# Knowledge chunk (retrieval unit)
# ---------------------------------------------------------------------------


class KnowledgeChunk(BaseModel):
    """
    A chunk of text derived from an artifact, ready for embedding and retrieval.

    This is the primary unit stored in the vector store.
    """

    chunk_id: str = Field(description="Unique chunk identifier")
    artifact_id: str = Field(description="ID of the source artifact")
    artifact_type: ArtifactType = Field(description="Type of the source artifact")
    repository: str = Field(description="Source repository")
    content: str = Field(description="Text content of the chunk")
    chunk_index: int = Field(
        description="Positional index of this chunk within the artifact"
    )
    total_chunks: Optional[int] = Field(
        default=None, description="Total number of chunks in the source artifact"
    )
    start_line: Optional[int] = Field(
        default=None, description="Start line in the original file (1-indexed)"
    )
    end_line: Optional[int] = Field(
        default=None, description="End line in the original file (1-indexed)"
    )
    token_count: Optional[int] = Field(
        default=None, description="Estimated token count for this chunk"
    )
    embedding: Optional[List[float]] = Field(
        default=None,
        description="Embedding vector — populated after embedding, not stored in JSON exports",
    )
    metadata: Dict[str, Any] = Field(
        default_factory=dict, description="Passthrough metadata from source artifact"
    )

    model_config = ConfigDict(use_enum_values=True)
