"""Tests for knowledge artifact schemas."""

from __future__ import annotations


from knowledge.schemas.artifacts import (
    ArtifactType,
    Commit,
    Issue,
    IssueSeverity,
    IssueStatus,
    KnowledgeChunk,
    ProgrammingLanguage,
    SourceFile,
    IncidentReport,
    ArchitectureDecision,
)


class TestSourceFile:
    def test_basic_creation(self):
        sf = SourceFile(
            artifact_id="file-001",
            repository="owner/repo",
            source_path="src/main.py",
            language=ProgrammingLanguage.PYTHON,
            line_count=100,
        )
        assert sf.artifact_type == ArtifactType.SOURCE_CODE
        assert sf.language == ProgrammingLanguage.PYTHON
        assert sf.is_test_file is False
        assert sf.imports == []
        assert sf.functions == []

    def test_default_artifact_type(self):
        sf = SourceFile(artifact_id="f-1", repository="r/r")
        assert sf.artifact_type == ArtifactType.SOURCE_CODE

    def test_serialisation_roundtrip(self):
        sf = SourceFile(
            artifact_id="file-002",
            repository="owner/repo",
            source_path="tests/test_app.py",
            is_test_file=True,
            functions=["test_one", "test_two"],
        )
        data = sf.model_dump()
        restored = SourceFile(**data)
        assert restored.artifact_id == sf.artifact_id
        assert restored.functions == ["test_one", "test_two"]
        assert restored.is_test_file is True


class TestCommit:
    def test_basic_commit(self):
        c = Commit(
            artifact_id="commit-001",
            repository="owner/repo",
            sha="abc1234567890",
            message="Fix critical bug in auth module",
            author_name="Dev Name",
        )
        assert c.artifact_type == ArtifactType.COMMIT
        assert c.sha == "abc1234567890"
        assert c.files_changed == []


class TestIssue:
    def test_basic_issue(self):
        issue = Issue(
            artifact_id="issue-001",
            repository="owner/repo",
            title="Null pointer exception in payment service",
            severity=IssueSeverity.HIGH,
            status=IssueStatus.OPEN,
        )
        assert issue.artifact_type == ArtifactType.ISSUE
        assert issue.severity == IssueSeverity.HIGH

    def test_issue_with_linked_prs(self):
        issue = Issue(
            artifact_id="issue-002",
            repository="owner/repo",
            title="Memory leak",
            linked_pull_requests=["pr-42", "pr-43"],
        )
        assert len(issue.linked_pull_requests) == 2


class TestKnowledgeChunk:
    def test_basic_chunk(self):
        chunk = KnowledgeChunk(
            chunk_id="chunk-001",
            artifact_id="file-001",
            artifact_type=ArtifactType.SOURCE_CODE,
            repository="owner/repo",
            content="def authenticate(user, token): ...",
            chunk_index=0,
        )
        assert chunk.chunk_id == "chunk-001"
        assert chunk.embedding is None
        assert chunk.metadata == {}

    def test_chunk_without_embedding(self):
        chunk = KnowledgeChunk(
            chunk_id="chunk-002",
            artifact_id="doc-001",
            artifact_type=ArtifactType.MARKDOWN,
            repository="owner/repo",
            content="# Authentication\nThis service handles auth.",
            chunk_index=1,
            total_chunks=5,
            token_count=15,
        )
        assert chunk.total_chunks == 5
        assert chunk.embedding is None  # Not populated until embedding step


class TestIncidentReport:
    def test_incident_creation(self):
        ir = IncidentReport(
            artifact_id="inc-001",
            repository="owner/repo",
            title="Database connection pool exhaustion",
            severity=IssueSeverity.CRITICAL,
            affected_services=["payment-service", "user-service"],
        )
        assert ir.artifact_type == ArtifactType.INCIDENT
        assert "payment-service" in ir.affected_services


class TestArchitectureDecision:
    def test_adr_creation(self):
        adr = ArchitectureDecision(
            artifact_id="adr-001",
            repository="owner/repo",
            title="Use event-driven architecture for order processing",
            decision_id="ADR-0001",
            status="accepted",
        )
        assert adr.artifact_type == ArtifactType.ARCHITECTURE_DECISION
        assert adr.decision_id == "ADR-0001"
