"""
Tests for FileIngestionSource and IngestionRegistry
"""

from pathlib import Path
import tempfile
import pytest

from ingestion.loaders.file_loader import FileIngestionSource
from ingestion.registry import IngestionRegistry
from knowledge.schemas.artifacts import ArtifactType, ProgrammingLanguage, SourceFile


@pytest.fixture
def temp_code_dir():
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        # Create Python source file
        py_file = root / "app.py"
        py_file.write_text(
            "import os\nfrom typing import List\n\nclass Server:\n    pass\n\ndef start():\n    pass\n",
            encoding="utf-8",
        )

        # Create Python test file
        test_dir = root / "tests"
        test_dir.mkdir()
        test_file = test_dir / "test_app.py"
        test_file.write_text(
            "def test_server():\n    assert True\n",
            encoding="utf-8",
        )

        # Create Markdown doc
        doc_file = root / "README.md"
        doc_file.write_text("# Project Title\n\nThis is docs.\n", encoding="utf-8")

        # Create Config file
        cfg_file = root / "config.yaml"
        cfg_file.write_text("server:\n  port: 8080\n", encoding="utf-8")

        # Create Excluded file (e.g. .pyc or in __pycache__)
        cache_dir = root / "__pycache__"
        cache_dir.mkdir()
        (cache_dir / "app.cpython-311.pyc").write_bytes(b"dummy")

        yield root


def test_file_loader_discovers_and_classifies_files(temp_code_dir):
    loader = FileIngestionSource(
        root_dir=temp_code_dir,
        repository_id="test/repo",
        commit_sha="abcdef123456",
        source_url_prefix="https://github.com/test/repo",
    )
    artifacts = list(loader.load())

    # Should find app.py, test_app.py, README.md, config.yaml (not the .pyc)
    assert len(artifacts) == 4

    # Check python file
    py_art = next(a for a in artifacts if a.source_path == "app.py")
    assert isinstance(py_art, SourceFile)
    assert py_art.language == ProgrammingLanguage.PYTHON
    assert py_art.is_test_file is False
    assert "Server" in py_art.classes
    assert "start" in py_art.functions
    assert "os" in py_art.imports
    assert py_art.commit_sha == "abcdef123456"

    # Check test file
    test_art = next(a for a in artifacts if "test_app.py" in a.source_path)
    assert isinstance(test_art, SourceFile)
    assert test_art.is_test_file is True

    # Check markdown file
    md_art = next(a for a in artifacts if a.source_path == "README.md")
    assert md_art.artifact_type == ArtifactType.MARKDOWN

    # Check yaml file
    cfg_art = next(a for a in artifacts if a.source_path == "config.yaml")
    assert cfg_art.artifact_type == ArtifactType.CONFIGURATION


def test_ingestion_registry():
    src = IngestionRegistry.create("file", root_dir=".", repository_id="local/repo")
    assert isinstance(src, FileIngestionSource)
