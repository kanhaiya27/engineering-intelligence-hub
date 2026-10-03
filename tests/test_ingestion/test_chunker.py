"""
Tests for CodeAwareChunker, DocAwareChunker, and ArtifactNormalizer
"""


from ingestion.processors.chunker import CodeAwareChunker, DocAwareChunker
from ingestion.processors.normalizer import ArtifactNormalizer
from knowledge.schemas.artifacts import ArtifactType, BaseArtifact, ProgrammingLanguage, SourceFile


def test_code_aware_chunker_ast_boundaries():
    code_content = (
        '"""Module docstring."""\n'
        'import sys\n\n'
        'class User:\n'
        '    def __init__(self, name: str):\n'
        '        self.name = name\n\n'
        'def helper_function(x: int) -> int:\n'
        '    return x * 2\n'
    )

    art = SourceFile(
        artifact_id="flask:src/user.py:1234",
        artifact_type=ArtifactType.SOURCE_CODE,
        repository="pallets/flask",
        source_path="src/user.py",
        language=ProgrammingLanguage.PYTHON,
        raw_content=code_content,
    )

    chunker = CodeAwareChunker(min_tokens_per_chunk=1)
    chunks = chunker.chunk(art)

    assert len(chunks) >= 2

    # Check class chunk
    class_chunk = next((c for c in chunks if c.metadata.get("symbol_name") == "User"), None)
    assert class_chunk is not None
    assert class_chunk.start_line == 4
    assert "class User:" in class_chunk.content
    assert class_chunk.metadata.get("chunk_type") == "class"

    # Check function chunk
    func_chunk = next((c for c in chunks if c.metadata.get("symbol_name") == "helper_function"), None)
    assert func_chunk is not None
    assert func_chunk.start_line == 8
    assert "def helper_function" in func_chunk.content


def test_doc_aware_chunker_headings():
    doc_content = (
        "# Installation Guide\n\n"
        "Run `pip install package`.\n\n"
        "## Quickstart\n\n"
        "Here is how to get started.\n"
    )

    art = BaseArtifact(
        artifact_id="flask:docs/install.md:1234",
        artifact_type=ArtifactType.MARKDOWN,
        repository="pallets/flask",
        source_path="docs/install.md",
        raw_content=doc_content,
    )

    chunker = DocAwareChunker()
    chunks = chunker.chunk(art)

    assert len(chunks) == 2
    assert chunks[0].metadata.get("section_title") == "Installation Guide"
    assert chunks[1].metadata.get("section_title") == "Quickstart"
    assert chunks[0].start_line == 1
    assert chunks[1].start_line == 5


def test_artifact_normalizer_pipeline():
    normalizer = ArtifactNormalizer()

    art = SourceFile(
        artifact_id="fastapi:fastapi/main.py:hash1",
        artifact_type=ArtifactType.SOURCE_CODE,
        repository="fastapi/fastapi",
        source_path="fastapi/main.py",
        language=ProgrammingLanguage.PYTHON,
        raw_content="\ufeffdef root():\r\n    return {'status': 'ok'}\r\n",
    )

    chunks = normalizer.process_artifact(art)
    assert len(chunks) > 0
    # BOM should be stripped
    assert not art.raw_content.startswith("\ufeff")
    assert "\r" not in art.raw_content
    # Deduplication test
    dup_chunks = normalizer.process_artifact(art)
    assert len(dup_chunks) == 0  # Ignored duplicate
