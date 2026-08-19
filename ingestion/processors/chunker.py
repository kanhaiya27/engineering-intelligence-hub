"""
Engineering Intelligence Hub — Code and Documentation Aware Chunkers
====================================================================
Implements structural boundary chunking for source code (functions, classes, methods,
modules) and semantic section chunking for documentation and engineering history.

Preserves exact source locations (start_line, end_line, file_path, symbol_name).
"""

from __future__ import annotations

import ast
import re
from typing import Any, Dict, List, Optional

import tiktoken

from ingestion.base import BaseChunker
from knowledge.schemas.artifacts import (
    ArtifactType,
    BaseArtifact,
    KnowledgeChunk,
    ProgrammingLanguage,
    SourceFile,
)


def _get_tokenizer():
    try:
        return tiktoken.get_encoding("cl100k_base")
    except Exception:
        return None


TOKENIZER = _get_tokenizer()


def estimate_tokens(text: str) -> int:
    """Estimate token count for a text string."""
    if not text:
        return 0
    if TOKENIZER:
        try:
            return len(TOKENIZER.encode(text, disallowed_special=()))
        except Exception:
            pass
    # Fallback heuristic: 1 token ~= 4 characters or 0.75 words
    return max(1, int(len(text) / 4))


class CodeAwareChunker(BaseChunker):
    """
    Code-aware chunker that uses AST parsing for Python and structural/line
    sliding windows for other programming languages.
    """

    def __init__(
        self,
        max_tokens_per_chunk: int = 512,
        min_tokens_per_chunk: int = 20,
        overlap_lines: int = 5,
    ) -> None:
        self.max_tokens_per_chunk = max_tokens_per_chunk
        self.min_tokens_per_chunk = min_tokens_per_chunk
        self.overlap_lines = overlap_lines

    @property
    def chunker_name(self) -> str:
        return "code_aware_ast_chunker"

    def _chunk_python_ast(
        self,
        artifact: BaseArtifact,
        content: str,
        lines: List[str],
    ) -> List[KnowledgeChunk]:
        """Chunk Python code using AST boundary detection."""
        chunks: List[KnowledgeChunk] = []
        try:
            tree = ast.parse(content)
        except Exception:
            return self._chunk_sliding_window(artifact, lines)

        # Collect top-level definitions
        nodes = []
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                nodes.append(node)

        if not nodes:
            return self._chunk_sliding_window(artifact, lines)

        # Sort nodes by line number
        nodes.sort(key=lambda n: n.lineno)

        chunk_idx = 0
        last_end_line = 0

        # Module preamble (imports, docstrings, module-level variables before first node)
        first_node_start = nodes[0].lineno
        if first_node_start > 1:
            preamble_lines = lines[: first_node_start - 1]
            preamble_text = "\n".join(preamble_lines).strip()
            if preamble_text and estimate_tokens(preamble_text) >= self.min_tokens_per_chunk:
                chunks.append(
                    KnowledgeChunk(
                        chunk_id=f"{artifact.artifact_id}:chunk:{chunk_idx}",
                        artifact_id=artifact.artifact_id,
                        artifact_type=artifact.artifact_type,
                        repository=artifact.repository,
                        content=preamble_text,
                        chunk_index=chunk_idx,
                        start_line=1,
                        end_line=first_node_start - 1,
                        token_count=estimate_tokens(preamble_text),
                        metadata={
                            "symbol_name": "<module_preamble>",
                            "chunk_type": "module_header",
                            "file_path": artifact.source_path,
                            "language": "python",
                            **artifact.metadata,
                        },
                    )
                )
                chunk_idx += 1
            last_end_line = first_node_start - 1

        # Process each top-level AST node
        for node in nodes:
            start_l = node.lineno
            end_l = getattr(node, "end_lineno", start_l + len(ast.unparse(node).splitlines()) if hasattr(ast, "unparse") else len(lines))
            end_l = min(end_l, len(lines))

            # Include any comments / decorator lines directly preceding if present
            node_lines = lines[start_l - 1 : end_l]
            node_text = "\n".join(node_lines).strip()

            symbol_name = node.name
            chunk_type = "class" if isinstance(node, ast.ClassDef) else "function"

            token_cnt = estimate_tokens(node_text)

            # If the class or function is excessively large, sub-chunk or break it down
            if token_cnt > self.max_tokens_per_chunk and isinstance(node, ast.ClassDef):
                # Sub-chunk class methods
                method_chunks = self._chunk_class_methods(artifact, node, lines, chunk_idx)
                if method_chunks:
                    chunks.extend(method_chunks)
                    chunk_idx += len(method_chunks)
                    last_end_line = end_l
                    continue

            chunks.append(
                KnowledgeChunk(
                    chunk_id=f"{artifact.artifact_id}:chunk:{chunk_idx}",
                    artifact_id=artifact.artifact_id,
                    artifact_type=artifact.artifact_type,
                    repository=artifact.repository,
                    content=node_text,
                    chunk_index=chunk_idx,
                    start_line=start_l,
                    end_line=end_l,
                    token_count=token_cnt,
                    metadata={
                        "symbol_name": symbol_name,
                        "chunk_type": chunk_type,
                        "file_path": artifact.source_path,
                        "language": "python",
                        **artifact.metadata,
                    },
                )
            )
            chunk_idx += 1
            last_end_line = end_l

        # Remaining trailing module code if any
        if last_end_line < len(lines):
            trailing_lines = lines[last_end_line:]
            trailing_text = "\n".join(trailing_lines).strip()
            if trailing_text and estimate_tokens(trailing_text) >= self.min_tokens_per_chunk:
                chunks.append(
                    KnowledgeChunk(
                        chunk_id=f"{artifact.artifact_id}:chunk:{chunk_idx}",
                        artifact_id=artifact.artifact_id,
                        artifact_type=artifact.artifact_type,
                        repository=artifact.repository,
                        content=trailing_text,
                        chunk_index=chunk_idx,
                        start_line=last_end_line + 1,
                        end_line=len(lines),
                        token_count=estimate_tokens(trailing_text),
                        metadata={
                            "symbol_name": "<module_trailer>",
                            "chunk_type": "module_trailer",
                            "file_path": artifact.source_path,
                            "language": "python",
                            **artifact.metadata,
                        },
                    )
                )

        # Set total_chunks for all
        total = len(chunks)
        for c in chunks:
            c.total_chunks = total

        return chunks if chunks else self._chunk_sliding_window(artifact, lines)

    def _chunk_class_methods(
        self,
        artifact: BaseArtifact,
        class_node: ast.ClassDef,
        lines: List[str],
        start_chunk_idx: int,
    ) -> List[KnowledgeChunk]:
        """Sub-chunk large classes into method chunks."""
        chunks: List[KnowledgeChunk] = []
        methods = [n for n in class_node.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
        if not methods:
            return []

        idx = start_chunk_idx
        class_header_lines = lines[class_node.lineno - 1 : methods[0].lineno - 1]
        header_text = "\n".join(class_header_lines).strip()
        if header_text:
            chunks.append(
                KnowledgeChunk(
                    chunk_id=f"{artifact.artifact_id}:chunk:{idx}",
                    artifact_id=artifact.artifact_id,
                    artifact_type=artifact.artifact_type,
                    repository=artifact.repository,
                    content=header_text,
                    chunk_index=idx,
                    start_line=class_node.lineno,
                    end_line=methods[0].lineno - 1,
                    token_count=estimate_tokens(header_text),
                    metadata={
                        "symbol_name": f"{class_node.name}.<header>",
                        "chunk_type": "class_header",
                        "file_path": artifact.source_path,
                        "language": "python",
                        **artifact.metadata,
                    },
                )
            )
            idx += 1

        for m in methods:
            m_start = m.lineno
            m_end = getattr(m, "end_lineno", m_start + len(ast.unparse(m).splitlines()) if hasattr(ast, "unparse") else len(lines))
            m_end = min(m_end, len(lines))
            m_lines = lines[m_start - 1 : m_end]
            m_text = "\n".join(m_lines).strip()
            chunks.append(
                KnowledgeChunk(
                    chunk_id=f"{artifact.artifact_id}:chunk:{idx}",
                    artifact_id=artifact.artifact_id,
                    artifact_type=artifact.artifact_type,
                    repository=artifact.repository,
                    content=m_text,
                    chunk_index=idx,
                    start_line=m_start,
                    end_line=m_end,
                    token_count=estimate_tokens(m_text),
                    metadata={
                        "symbol_name": f"{class_node.name}.{m.name}",
                        "chunk_type": "method",
                        "file_path": artifact.source_path,
                        "language": "python",
                        **artifact.metadata,
                    },
                )
            )
            idx += 1

        return chunks

    def _chunk_sliding_window(
        self,
        artifact: BaseArtifact,
        lines: List[str],
    ) -> List[KnowledgeChunk]:
        """Safe fallback sliding window chunker."""
        chunks: List[KnowledgeChunk] = []
        total_lines = len(lines)
        if total_lines == 0:
            return []

        # Target ~40 lines per chunk with overlap
        target_lines_per_chunk = 40
        step = max(1, target_lines_per_chunk - self.overlap_lines)

        chunk_idx = 0
        for start_idx in range(0, total_lines, step):
            end_idx = min(start_idx + target_lines_per_chunk, total_lines)
            chunk_lines = lines[start_idx:end_idx]
            chunk_text = "\n".join(chunk_lines).strip()

            if not chunk_text:
                continue

            chunks.append(
                KnowledgeChunk(
                    chunk_id=f"{artifact.artifact_id}:chunk:{chunk_idx}",
                    artifact_id=artifact.artifact_id,
                    artifact_type=artifact.artifact_type,
                    repository=artifact.repository,
                    content=chunk_text,
                    chunk_index=chunk_idx,
                    start_line=start_idx + 1,
                    end_line=end_idx,
                    token_count=estimate_tokens(chunk_text),
                    metadata={
                        "symbol_name": None,
                        "chunk_type": "code_block",
                        "file_path": artifact.source_path,
                        **artifact.metadata,
                    },
                )
            )
            chunk_idx += 1

            if end_idx >= total_lines:
                break

        total = len(chunks)
        for c in chunks:
            c.total_chunks = total

        return chunks

    def chunk(self, artifact: BaseArtifact) -> List[KnowledgeChunk]:
        content = artifact.raw_content or ""
        lines = content.splitlines()
        if not lines:
            return []

        # Check if Python source
        is_python = False
        if isinstance(artifact, SourceFile) and artifact.language == ProgrammingLanguage.PYTHON:
            is_python = True
        elif artifact.source_path and artifact.source_path.endswith(".py"):
            is_python = True

        if is_python:
            return self._chunk_python_ast(artifact, content, lines)
        return self._chunk_sliding_window(artifact, lines)


class DocAwareChunker(BaseChunker):
    """
    Heading-aware chunker for Markdown, RST, and plain text documentation.
    """

    def __init__(
        self,
        max_tokens_per_chunk: int = 512,
        min_tokens_per_chunk: int = 15,
    ) -> None:
        self.max_tokens_per_chunk = max_tokens_per_chunk
        self.min_tokens_per_chunk = min_tokens_per_chunk

    @property
    def chunker_name(self) -> str:
        return "doc_aware_heading_chunker"

    def chunk(self, artifact: BaseArtifact) -> List[KnowledgeChunk]:
        content = artifact.raw_content or ""
        lines = content.splitlines()
        if not lines:
            return []

        # Find heading lines (# Heading, ## Heading, ### Heading, or underline headings)
        heading_pattern = re.compile(r"^(#{1,6})\s+(.+)$")
        rst_heading_chars = set("=-~`#*^+\"':")

        sections: List[tuple[str, int, int, List[str]]] = []  # (heading_title, start_l, end_l, lines)
        current_heading = "Introduction"
        current_start = 1
        current_lines: List[str] = []

        for i, line in enumerate(lines, start=1):
            m = heading_pattern.match(line)
            is_rst_heading = False
            if i < len(lines) and len(lines[i]) >= 3 and all(c == lines[i][0] for c in lines[i]) and lines[i][0] in rst_heading_chars:
                is_rst_heading = True

            if m or is_rst_heading:
                if current_lines:
                    sections.append((current_heading, current_start, i - 1, current_lines))
                    current_lines = []
                current_heading = m.group(2) if m else line.strip()
                current_start = i

            current_lines.append(line)

        if current_lines:
            sections.append((current_heading, current_start, len(lines), current_lines))

        chunks: List[KnowledgeChunk] = []
        chunk_idx = 0

        for title, start_l, end_l, sec_lines in sections:
            sec_text = "\n".join(sec_lines).strip()
            if not sec_text:
                continue

            sec_tokens = estimate_tokens(sec_text)
            if sec_tokens <= self.max_tokens_per_chunk:
                chunks.append(
                    KnowledgeChunk(
                        chunk_id=f"{artifact.artifact_id}:chunk:{chunk_idx}",
                        artifact_id=artifact.artifact_id,
                        artifact_type=artifact.artifact_type,
                        repository=artifact.repository,
                        content=sec_text,
                        chunk_index=chunk_idx,
                        start_line=start_l,
                        end_line=end_l,
                        token_count=sec_tokens,
                        metadata={
                            "section_title": title,
                            "chunk_type": "doc_section",
                            "file_path": artifact.source_path,
                            **artifact.metadata,
                        },
                    )
                )
                chunk_idx += 1
            else:
                # Sub-split long section by paragraphs
                paragraphs = sec_text.split("\n\n")
                sub_buf: List[str] = []
                sub_tokens = 0
                sub_start = start_l

                for p in paragraphs:
                    p_tok = estimate_tokens(p)
                    if sub_tokens + p_tok > self.max_tokens_per_chunk and sub_buf:
                        buf_text = "\n\n".join(sub_buf).strip()
                        chunks.append(
                            KnowledgeChunk(
                                chunk_id=f"{artifact.artifact_id}:chunk:{chunk_idx}",
                                artifact_id=artifact.artifact_id,
                                artifact_type=artifact.artifact_type,
                                repository=artifact.repository,
                                content=buf_text,
                                chunk_index=chunk_idx,
                                start_line=sub_start,
                                end_line=end_l,
                                token_count=estimate_tokens(buf_text),
                                metadata={
                                    "section_title": title,
                                    "chunk_type": "doc_paragraph_block",
                                    "file_path": artifact.source_path,
                                    **artifact.metadata,
                                },
                            )
                        )
                        chunk_idx += 1
                        sub_buf = [p]
                        sub_tokens = p_tok
                    else:
                        sub_buf.append(p)
                        sub_tokens += p_tok

                if sub_buf:
                    buf_text = "\n\n".join(sub_buf).strip()
                    chunks.append(
                        KnowledgeChunk(
                            chunk_id=f"{artifact.artifact_id}:chunk:{chunk_idx}",
                            artifact_id=artifact.artifact_id,
                            artifact_type=artifact.artifact_type,
                            repository=artifact.repository,
                            content=buf_text,
                            chunk_index=chunk_idx,
                            start_line=sub_start,
                            end_line=end_l,
                            token_count=estimate_tokens(buf_text),
                            metadata={
                                "section_title": title,
                                "chunk_type": "doc_paragraph_block",
                                "file_path": artifact.source_path,
                                **artifact.metadata,
                            },
                        )
                    )
                    chunk_idx += 1

        total = len(chunks)
        for c in chunks:
            c.total_chunks = total

        return chunks


class UniversalChunker(BaseChunker):
    """
    Universal chunker that routes to CodeAwareChunker or DocAwareChunker
    based on artifact type.
    """

    def __init__(
        self,
        code_chunker: Optional[CodeAwareChunker] = None,
        doc_chunker: Optional[DocAwareChunker] = None,
    ) -> None:
        self.code_chunker = code_chunker or CodeAwareChunker()
        self.doc_chunker = doc_chunker or DocAwareChunker()

    @property
    def chunker_name(self) -> str:
        return "universal_adaptive_chunker"

    def chunk(self, artifact: BaseArtifact) -> List[KnowledgeChunk]:
        if artifact.artifact_type in (ArtifactType.SOURCE_CODE, ArtifactType.TEST):
            return self.code_chunker.chunk(artifact)
        return self.doc_chunker.chunk(artifact)
