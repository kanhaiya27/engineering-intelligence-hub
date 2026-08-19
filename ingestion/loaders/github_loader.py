"""
Engineering Intelligence Hub — GitHub Repository Ingestion Loader
==================================================================
Ingests repository source files, Git commit history, and GitHub engineering artifacts
(issues, pull requests) at a fixed, pinned commit or tag.

Ensures strict source provenance across all generated artifacts.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional

from core.logging import get_logger
from ingestion.base import BaseIngestionSource
from ingestion.loaders.file_loader import FileIngestionSource
from knowledge.schemas.artifacts import (
    ArtifactType,
    BaseArtifact,
    Commit,
    Issue,
    IssueSeverity,
    IssueStatus,
    PullRequest,
)

logger = get_logger(__name__)


class GitHubRepositoryIngestionSource(BaseIngestionSource):
    """
    Ingests source files, commit history, and issues/PRs from a GitHub repository.
    """

    def __init__(
        self,
        repository: str,  # "owner/repo" or "repo"
        clone_url: Optional[str] = None,
        target_commit_or_tag: Optional[str] = None,
        local_repo_path: Optional[str | Path] = None,
        include_commits: bool = True,
        max_commits: int = 100,
        issues_data: Optional[List[Dict[str, Any]]] = None,
        pull_requests_data: Optional[List[Dict[str, Any]]] = None,
    ) -> None:
        self.repository = repository
        self.clone_url = clone_url or f"https://github.com/{repository}.git"
        self.target_commit_or_tag = target_commit_or_tag
        self.local_repo_path = Path(local_repo_path).resolve() if local_repo_path else None
        self.include_commits = include_commits
        self.max_commits = max_commits
        self.issues_data = issues_data or []
        self.pull_requests_data = pull_requests_data or []
        self._temp_dir: Optional[tempfile.TemporaryDirectory] = None

    @property
    def source_type(self) -> ArtifactType:
        return ArtifactType.SOURCE_CODE

    @property
    def source_id(self) -> str:
        ref = self.target_commit_or_tag or "HEAD"
        return f"github:{self.repository}@{ref}"

    def validate_config(self) -> bool:
        if not self.local_repo_path and not self.clone_url:
            raise ValueError("Either local_repo_path or clone_url must be provided.")
        if self.local_repo_path and not self.local_repo_path.exists():
            raise FileNotFoundError(f"Local repo path not found: {self.local_repo_path}")
        return True

    def _ensure_local_checkout(self) -> Path:
        """Ensure the repository is available locally at the requested commit/tag."""
        if self.local_repo_path and self.local_repo_path.exists():
            return self.local_repo_path

        # Clone into a temp directory
        self._temp_dir = tempfile.TemporaryDirectory(prefix=f"eih_repo_{self.repository.replace('/', '_')}_")
        repo_dir = Path(self._temp_dir.name)

        logger.info(f"Cloning {self.clone_url} to {repo_dir}...")
        clone_cmd = ["git", "clone"]
        if self.target_commit_or_tag:
            # Try single branch / tag clone if possible
            clone_cmd.extend(["--branch", self.target_commit_or_tag, "--depth", "1", self.clone_url, str(repo_dir)])
            res = subprocess.run(clone_cmd, capture_output=True, text=True)
            if res.returncode != 0:
                # If target was a commit SHA rather than branch/tag, full clone and checkout
                logger.info(f"Branch clone failed, falling back to full clone for commit checkout...")
                shutil.rmtree(repo_dir, ignore_errors=True)
                repo_dir.mkdir(parents=True, exist_ok=True)
                subprocess.run(["git", "clone", self.clone_url, str(repo_dir)], check=True, capture_output=True)
                subprocess.run(["git", "checkout", self.target_commit_or_tag], cwd=str(repo_dir), check=True, capture_output=True)
        else:
            clone_cmd.extend(["--depth", "1", self.clone_url, str(repo_dir)])
            subprocess.run(clone_cmd, check=True, capture_output=True)

        return repo_dir

    def _get_head_commit_sha(self, repo_path: Path) -> str:
        """Get the current commit SHA of the checked-out repository."""
        try:
            res = subprocess.run(["git", "rev-parse", "HEAD"], cwd=str(repo_path), capture_output=True, text=True, check=True)
            return res.stdout.strip()
        except Exception:
            return self.target_commit_or_tag or "unknown"

    def _load_git_commits(self, repo_path: Path) -> Iterator[Commit]:
        """Parse git log and yield Commit artifacts."""
        try:
            # Format: SHA%x1fAuthor%x1fEmail%x1fDate%x1fSubject%x1e
            cmd = ["git", "log", f"-n{self.max_commits}", "--format=%H%x1f%an%x1f%ae%x1f%aI%x1f%s%x1e", "--name-only"]
            res = subprocess.run(cmd, cwd=str(repo_path), capture_output=True, text=True)
            if res.returncode != 0:
                return

            raw_entries = res.stdout.split("\x1e")
            for entry in raw_entries:
                entry = entry.strip()
                if not entry:
                    continue

                parts = entry.split("\x1f")
                if len(parts) < 5:
                    continue

                sha = parts[0].strip()
                author_name = parts[1].strip()
                author_email = parts[2].strip()
                committed_at = parts[3].strip()
                
                rest = parts[4].split("\n", 1)
                message = rest[0].strip()
                files_changed: List[str] = []
                if len(rest) > 1:
                    files_changed = [f.strip() for f in rest[1].splitlines() if f.strip()]

                yield Commit(
                    artifact_id=f"{self.repository}:commit:{sha}",
                    artifact_type=ArtifactType.COMMIT,
                    repository=self.repository,
                    sha=sha,
                    author_name=author_name,
                    author_email=author_email,
                    committed_at=committed_at,
                    message=message,
                    files_changed=files_changed,
                    raw_content=f"Commit: {sha}\nAuthor: {author_name} <{author_email}>\nDate: {committed_at}\n\n{message}\n\nFiles changed:\n" + "\n".join(files_changed),
                    metadata={
                        "repository": self.repository,
                        "source_url": f"https://github.com/{self.repository}/commit/{sha}",
                    },
                )
        except Exception as e:
            logger.warning(f"Failed to read git log: {e}")

    def load(self) -> Iterator[BaseArtifact]:
        """Synchronously load files, commits, and GitHub issues/PRs."""
        self.validate_config()
        repo_path = self._ensure_local_checkout()
        commit_sha = self._get_head_commit_sha(repo_path)
        source_url_prefix = f"https://github.com/{self.repository}"

        # 1. Ingest all source, doc, and config files via FileIngestionSource
        file_loader = FileIngestionSource(
            root_dir=repo_path,
            repository_id=self.repository,
            commit_sha=commit_sha,
            source_url_prefix=source_url_prefix,
        )
        for artifact in file_loader.load():
            yield artifact

        # 2. Ingest Git commits
        if self.include_commits and (repo_path / ".git").exists():
            for commit_art in self._load_git_commits(repo_path):
                yield commit_art

        # 3. Ingest Issues (if supplied)
        for issue_dict in self.issues_data:
            issue_num = issue_dict.get("number")
            title = issue_dict.get("title", "")
            body = issue_dict.get("body", "")
            status_val = issue_dict.get("status", "open").lower()
            status = IssueStatus.CLOSED if status_val == "closed" else IssueStatus.OPEN

            yield Issue(
                artifact_id=f"{self.repository}:issue:{issue_num}",
                artifact_type=ArtifactType.ISSUE,
                repository=self.repository,
                issue_number=issue_num,
                title=title,
                body=body,
                author=issue_dict.get("author"),
                labels=issue_dict.get("labels", []),
                status=status,
                created_at=issue_dict.get("created_at"),
                closed_at=issue_dict.get("closed_at"),
                raw_content=f"Issue #{issue_num}: {title}\n\n{body}",
                metadata={
                    "repository": self.repository,
                    "source_url": f"https://github.com/{self.repository}/issues/{issue_num}",
                    "labels": issue_dict.get("labels", []),
                },
            )

        # 4. Ingest Pull Requests (if supplied)
        for pr_dict in self.pull_requests_data:
            pr_num = pr_dict.get("number")
            title = pr_dict.get("title", "")
            body = pr_dict.get("body", "")

            yield PullRequest(
                artifact_id=f"{self.repository}:pr:{pr_num}",
                artifact_type=ArtifactType.PULL_REQUEST,
                repository=self.repository,
                pr_number=pr_num,
                title=title,
                body=body,
                author=pr_dict.get("author"),
                labels=pr_dict.get("labels", []),
                merged_at=pr_dict.get("merged_at"),
                merge_commit_sha=pr_dict.get("merge_commit_sha"),
                files_changed=pr_dict.get("files_changed", []),
                raw_content=f"Pull Request #{pr_num}: {title}\n\n{body}",
                metadata={
                    "repository": self.repository,
                    "source_url": f"https://github.com/{self.repository}/pull/{pr_num}",
                },
            )
