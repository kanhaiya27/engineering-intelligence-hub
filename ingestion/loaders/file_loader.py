"""
Engineering Intelligence Hub — File & Directory Ingestion Loader
================================================================
Recursively scans local filesystem directories and yields typed BaseArtifact
instances (SourceFile, TestCase, BaseArtifact for docs/config).

Features:
- Configurable include/exclude file patterns.
- Automatic language classification.
- Test file detection and classification.
- AST-based symbol extraction for Python (functions, classes, imports).
- Preserves full source provenance (repository, file path, line count, size).
"""

from __future__ import annotations

import ast
import hashlib
import os
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional, Set

from core.logging import get_logger
from ingestion.base import BaseIngestionSource
from knowledge.schemas.artifacts import (
    ArtifactType,
    BaseArtifact,
    ProgrammingLanguage,
    SourceFile,
    TestCase,
)

logger = get_logger(__name__)

# Default excluded directory names
DEFAULT_EXCLUDED_DIRS: Set[str] = {
    ".git",
    "node_modules",
    ".venv",
    "venv",
    "env",
    ".env",
    "build",
    "dist",
    "target",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    ".idea",
    ".vscode",
    "vendor",
    "egg-info",
    ".eggs",
}

# Default excluded file extensions (compiled/binary/cache)
DEFAULT_EXCLUDED_EXTENSIONS: Set[str] = {
    ".pyc",
    ".pyo",
    ".pyd",
    ".class",
    ".o",
    ".obj",
    ".so",
    ".dll",
    ".dylib",
    ".exe",
    ".bin",
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".ico",
    ".svg",
    ".pdf",
    ".zip",
    ".tar",
    ".gz",
    ".7z",
    ".woff",
    ".woff2",
    ".ttf",
    ".eot",
    ".mp4",
    ".mp3",
    ".wav",
}

# Mapping of file extensions to ProgrammingLanguage and ArtifactType
EXTENSION_MAP: Dict[str, tuple[ProgrammingLanguage, ArtifactType]] = {
    # Source Code
    ".py": (ProgrammingLanguage.PYTHON, ArtifactType.SOURCE_CODE),
    ".js": (ProgrammingLanguage.JAVASCRIPT, ArtifactType.SOURCE_CODE),
    ".ts": (ProgrammingLanguage.TYPESCRIPT, ArtifactType.SOURCE_CODE),
    ".jsx": (ProgrammingLanguage.JAVASCRIPT, ArtifactType.SOURCE_CODE),
    ".tsx": (ProgrammingLanguage.TYPESCRIPT, ArtifactType.SOURCE_CODE),
    ".java": (ProgrammingLanguage.JAVA, ArtifactType.SOURCE_CODE),
    ".go": (ProgrammingLanguage.GO, ArtifactType.SOURCE_CODE),
    ".rs": (ProgrammingLanguage.RUST, ArtifactType.SOURCE_CODE),
    ".cpp": (ProgrammingLanguage.CPP, ArtifactType.SOURCE_CODE),
    ".cc": (ProgrammingLanguage.CPP, ArtifactType.SOURCE_CODE),
    ".cxx": (ProgrammingLanguage.CPP, ArtifactType.SOURCE_CODE),
    ".c": (ProgrammingLanguage.C, ArtifactType.SOURCE_CODE),
    ".h": (ProgrammingLanguage.C, ArtifactType.SOURCE_CODE),
    ".hpp": (ProgrammingLanguage.CPP, ArtifactType.SOURCE_CODE),
    ".cs": (ProgrammingLanguage.CSHARP, ArtifactType.SOURCE_CODE),
    ".rb": (ProgrammingLanguage.RUBY, ArtifactType.SOURCE_CODE),
    ".kt": (ProgrammingLanguage.KOTLIN, ArtifactType.SOURCE_CODE),
    ".scala": (ProgrammingLanguage.SCALA, ArtifactType.SOURCE_CODE),
    ".sh": (ProgrammingLanguage.SHELL, ArtifactType.SOURCE_CODE),
    ".bash": (ProgrammingLanguage.SHELL, ArtifactType.SOURCE_CODE),
    ".sql": (ProgrammingLanguage.SQL, ArtifactType.SOURCE_CODE),
    # Documentation
    ".md": (ProgrammingLanguage.OTHER, ArtifactType.MARKDOWN),
    ".markdown": (ProgrammingLanguage.OTHER, ArtifactType.MARKDOWN),
    ".txt": (ProgrammingLanguage.OTHER, ArtifactType.PLAIN_TEXT),
    ".rst": (ProgrammingLanguage.OTHER, ArtifactType.MARKDOWN),
    # Configuration
    ".yaml": (ProgrammingLanguage.YAML, ArtifactType.CONFIGURATION),
    ".yml": (ProgrammingLanguage.YAML, ArtifactType.CONFIGURATION),
    ".json": (ProgrammingLanguage.JSON, ArtifactType.CONFIGURATION),
    ".toml": (ProgrammingLanguage.TOML, ArtifactType.CONFIGURATION),
}


class FileIngestionSource(BaseIngestionSource):
    """
    Ingests files from a local directory.
    """

    def __init__(
        self,
        root_dir: str | Path,
        repository_id: str,
        commit_sha: Optional[str] = None,
        source_url_prefix: Optional[str] = None,
        max_file_size_bytes: int = 1_048_576,  # 1 MB
        excluded_dirs: Optional[Set[str]] = None,
        excluded_extensions: Optional[Set[str]] = None,
        supported_extensions: Optional[Set[str]] = None,
    ) -> None:
        self.root_dir = Path(root_dir).resolve()
        self.repository_id = repository_id
        self.commit_sha = commit_sha
        self.source_url_prefix = source_url_prefix
        self.max_file_size_bytes = max_file_size_bytes
        self.excluded_dirs = excluded_dirs or DEFAULT_EXCLUDED_DIRS
        self.excluded_extensions = excluded_extensions or DEFAULT_EXCLUDED_EXTENSIONS
        self.supported_extensions = supported_extensions or set(EXTENSION_MAP.keys())

    @property
    def source_type(self) -> ArtifactType:
        return ArtifactType.SOURCE_CODE

    @property
    def source_id(self) -> str:
        return f"file:{self.repository_id}:{self.root_dir}"

    def validate_config(self) -> bool:
        if not self.root_dir.exists():
            raise FileNotFoundError(f"Root directory does not exist: {self.root_dir}")
        if not self.root_dir.is_dir():
            raise NotADirectoryError(f"Root path is not a directory: {self.root_dir}")
        return True

    def _is_test_file(self, relative_path: str, filename: str) -> bool:
        """Heuristic check to determine if a file is a test file."""
        norm_path = relative_path.replace("\\", "/").lower()
        norm_name = filename.lower()

        # Path heuristics
        if any(part in ["tests", "test", "__tests__", "spec", "specs"] for part in norm_path.split("/")):
            return True

        # Filename heuristics
        if norm_name.startswith("test_") or norm_name.endswith("_test.py") or norm_name.endswith("test.py"):
            return True
        if norm_name.endswith(".spec.ts") or norm_name.endswith(".spec.js"):
            return True
        if norm_name.endswith(".test.ts") or norm_name.endswith(".test.js"):
            return True
        if norm_name.endswith("test.java") or norm_name.endswith("tests.java"):
            return True

        return False

    def _extract_python_symbols(self, content: str) -> tuple[List[str], List[str], List[str]]:
        """Extract top-level imports, classes, and functions from Python source."""
        imports: List[str] = []
        classes: List[str] = []
        functions: List[str] = []

        try:
            tree = ast.parse(content)
            for node in tree.body:
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        imports.append(alias.name)
                elif isinstance(node, ast.ImportFrom):
                    module = node.module or ""
                    for alias in node.names:
                        imports.append(f"{module}.{alias.name}" if module else alias.name)
                elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    functions.append(node.name)
                elif isinstance(node, ast.ClassDef):
                    classes.append(node.name)
        except Exception:
            # AST parsing may fail on syntax errors or non-standard syntax; fall back safely
            pass

        return imports, classes, functions

    def load(self) -> Iterator[BaseArtifact]:
        """Synchronously walk directory and yield typed artifacts."""
        self.validate_config()

        for dirpath, dirnames, filenames in os.walk(self.root_dir):
            # Modify dirnames in-place to skip excluded directories
            dirnames[:] = [d for d in dirnames if d not in self.excluded_dirs and not d.startswith(".")]

            for filename in filenames:
                file_path = Path(dirpath) / filename
                suffix = file_path.suffix.lower()

                if suffix in self.excluded_extensions:
                    continue

                if self.supported_extensions and suffix not in self.supported_extensions:
                    continue

                try:
                    size_bytes = file_path.stat().st_size
                except OSError:
                    continue

                if size_bytes > self.max_file_size_bytes or size_bytes == 0:
                    continue

                try:
                    content = file_path.read_text(encoding="utf-8", errors="replace")
                except Exception as e:
                    logger.warning(f"Failed to read file {file_path}: {e}")
                    continue

                rel_path = str(file_path.relative_to(self.root_dir)).replace("\\", "/")
                is_test = self._is_test_file(rel_path, filename)
                lang, art_type = EXTENSION_MAP.get(suffix, (ProgrammingLanguage.UNKNOWN, ArtifactType.UNKNOWN))

                # Build unique artifact_id
                content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()[:16]
                artifact_id = f"{self.repository_id}:{rel_path}:{content_hash}"

                source_url = None
                if self.source_url_prefix:
                    ref = self.commit_sha or "main"
                    source_url = f"{self.source_url_prefix.rstrip('/')}/blob/{ref}/{rel_path}"

                lines = content.splitlines()
                line_count = len(lines)

                metadata: Dict[str, Any] = {
                    "extension": suffix,
                    "filename": filename,
                    "is_test": is_test,
                    "source_url": source_url,
                }
                if self.commit_sha:
                    metadata["commit_sha"] = self.commit_sha

                if art_type == ArtifactType.SOURCE_CODE:
                    imports, classes, functions = [], [], []
                    if lang == ProgrammingLanguage.PYTHON:
                        imports, classes, functions = self._extract_python_symbols(content)

                    yield SourceFile(
                        artifact_id=artifact_id,
                        artifact_type=ArtifactType.SOURCE_CODE,
                        repository=self.repository_id,
                        source_path=rel_path,
                        raw_content=content,
                        language=lang,
                        size_bytes=size_bytes,
                        line_count=line_count,
                        is_test_file=is_test,
                        imports=imports,
                        classes=classes,
                        functions=functions,
                        commit_sha=self.commit_sha,
                        metadata=metadata,
                    )
                else:
                    yield BaseArtifact(
                        artifact_id=artifact_id,
                        artifact_type=art_type,
                        repository=self.repository_id,
                        source_path=rel_path,
                        raw_content=content,
                        metadata=metadata,
                    )

    def estimate_artifact_count(self) -> Optional[int]:
        count = 0
        for dirpath, dirnames, filenames in os.walk(self.root_dir):
            dirnames[:] = [d for d in dirnames if d not in self.excluded_dirs and not d.startswith(".")]
            for f in filenames:
                suffix = Path(f).suffix.lower()
                if suffix not in self.excluded_extensions and suffix in self.supported_extensions:
                    count += 1
        return count
