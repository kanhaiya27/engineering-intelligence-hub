"""
Engineering Intelligence Hub — Code and Documentation Aware Chunkers
====================================================================
Implements structural boundary chunking for source code (functions, classes, methods,
modules) and semantic section chunking for documentation and engineering history
(original plan §6.2: Python on AST symbol boundaries, oversized classes decomposed by
method; Markdown/RST header-aware; configuration and text with provenance).

Three guarantees (fixed 2026-10-05; before, 3,485 of 48,046 chunks were longer than the
embedding model can read and content between top-level definitions was dropped):

  1. **Size** — every chunk fits the embedding model's input window. Tokens are counted
     with the embedding model's OWN tokenizer (BGE-small: 512 incl. [CLS]/[SEP]); the old
     count used tiktoken (a GPT tokenizer), which undercounts code and docs for BGE, so
     the tail of long chunks was silently never embedded.
  2. **Coverage** — every non-blank line of a file is in a chunk: module code between
     definitions, decorators, class bodies between methods and short import headers
     (formerly dropped below `min_tokens_per_chunk`, which is now unused) are kept.
  3. **Provenance** — every chunk carries its exact start_line / end_line, including the
     pieces of a split unit (sub-chunks used to get the whole section's end line).

Structure first, size second: a unit (function, class, method, section, paragraph) is
split by lines only when it alone is larger than the window; a single line larger than
the window is split by words. Split pieces keep their symbol / section name and record
"part" / "parts".
"""

from __future__ import annotations

import ast
import re
from functools import lru_cache
from typing import Dict, List, Optional, Tuple

from ingestion.base import BaseChunker
from knowledge.schemas.artifacts import (
    ArtifactType,
    BaseArtifact,
    KnowledgeChunk,
    ProgrammingLanguage,
    SourceFile,
)

# BERT-style tokenizers add [CLS] and [SEP] to every input.
_SPECIAL_TOKENS = 2


@lru_cache(maxsize=1)
def _embedding_tokenizer():
    """The tokenizer of the embedding model the chunks are embedded with."""
    from transformers import AutoTokenizer

    from core.config import settings

    tok = AutoTokenizer.from_pretrained(settings.vector_store.embedding_model)
    tok.model_max_length = 10**9  # counting only: no truncation, no length warnings
    return tok


def _content_tokens(text: str) -> int:
    """Tokens of `text` for the embedding model, WITHOUT special tokens."""
    if not text:
        return 0
    return len(_embedding_tokenizer()(text, add_special_tokens=False)["input_ids"])


def estimate_tokens(text: str) -> int:
    """Exact input length of `text` for the embedding model (incl. special tokens)."""
    if not text:
        return 0
    return _content_tokens(text) + _SPECIAL_TOKENS


def embedding_tokenizer_name() -> str:
    from core.config import settings

    return settings.vector_store.embedding_model


# A unit is a structural piece of a file before size limits are applied:
# (start_line, end_line, metadata)  — 1-based, inclusive.
Unit = Tuple[int, int, Dict]


class _Splitter:
    """Packs lines into pieces that fit the embedding window, keeping exact line ranges."""

    def __init__(self, max_tokens: int) -> None:
        self.budget = max_tokens - _SPECIAL_TOKENS  # content tokens available per chunk

    def fits(self, text: str) -> bool:
        return _content_tokens(text) <= self.budget

    def split(self, lines: List[str], first_line_no: int, overlap_lines: int = 0) -> List[Tuple[int, int, str]]:
        """Split lines[i] (line number first_line_no + i) into (start, end, text) pieces.

        BERT tokenisation never merges tokens across whitespace, so the tokens of lines
        joined by newlines are the sum of the per-line tokens; pieces are packed with
        that sum and every piece is checked with an exact count.
        """
        counts = [_content_tokens(l) for l in lines]
        pieces: List[Tuple[int, int, str]] = []
        i = 0
        while i < len(lines):
            if not lines[i].strip():
                i += 1
                continue
            if counts[i] > self.budget:  # one line alone is too long: split it by words
                pieces.extend(self._split_line(lines[i], first_line_no + i))
                i += 1
                continue
            j, used = i, 0
            while j < len(lines) and counts[j] <= self.budget and used + counts[j] <= self.budget:
                used += counts[j]
                j += 1
            pieces.append(self._piece(lines, i, j - 1, first_line_no))
            if j >= len(lines):
                break
            # optional overlap for sliding windows; always make progress
            i = max(i + 1, j - overlap_lines) if overlap_lines and j - i > overlap_lines else j
        return [p for p in pieces if p[2]]

    @staticmethod
    def _piece(lines: List[str], i: int, j: int, first_line_no: int) -> Tuple[int, int, str]:
        while i < j and not lines[i].strip():
            i += 1
        while j > i and not lines[j].strip():
            j -= 1
        return first_line_no + i, first_line_no + j, "\n".join(lines[i: j + 1]).strip()

    def _longest_fitting_prefix(self, text: str) -> int:
        """Largest k such that text[:k] fits the budget (exact count, binary search)."""
        lo, hi = 1, len(text)
        while lo < hi:
            mid = (lo + hi + 1) // 2
            if _content_tokens(text[:mid]) <= self.budget:
                lo = mid
            else:
                hi = mid - 1
        return lo

    def _split_line(self, line: str, line_no: int) -> List[Tuple[int, int, str]]:
        pieces, buf, used = [], [], 0
        for word in re.split(r"(\s+)", line):
            if not word:
                continue
            n = _content_tokens(word)
            if n > self.budget:  # a single "word" (e.g. minified code, base64): slice it
                if buf:
                    pieces.append((line_no, line_no, "".join(buf).strip()))
                    buf, used = [], 0
                rest = word
                while rest:
                    cut = self._longest_fitting_prefix(rest)
                    pieces.append((line_no, line_no, rest[:cut]))
                    rest = rest[cut:]
                continue
            if used + n > self.budget and buf:
                pieces.append((line_no, line_no, "".join(buf).strip()))
                buf, used = [], 0
            buf.append(word)
            used += n
        if buf and "".join(buf).strip():
            pieces.append((line_no, line_no, "".join(buf).strip()))
        return pieces


def _build_chunks(
    artifact: BaseArtifact,
    lines: List[str],
    units: List[Unit],
    splitter: _Splitter,
    overlap_lines: int = 0,
) -> List[KnowledgeChunk]:
    chunks: List[KnowledgeChunk] = []
    for start, end, meta in units:
        unit_lines = lines[start - 1: end]
        text = "\n".join(unit_lines).strip()
        if not text:
            continue
        if splitter.fits(text):
            s, e, t = _Splitter._piece(unit_lines, 0, len(unit_lines) - 1, start)
            pieces = [(s, e, t)]
        else:
            pieces = splitter.split(unit_lines, start, overlap_lines=overlap_lines)
        for part, (s, e, t) in enumerate(pieces, start=1):
            idx = len(chunks)
            extra = {"part": part, "parts": len(pieces)} if len(pieces) > 1 else {}
            chunks.append(
                KnowledgeChunk(
                    chunk_id=f"{artifact.artifact_id}:chunk:{idx}",
                    artifact_id=artifact.artifact_id,
                    artifact_type=artifact.artifact_type,
                    repository=artifact.repository,
                    content=t,
                    chunk_index=idx,
                    start_line=s,
                    end_line=e,
                    token_count=estimate_tokens(t),
                    metadata={
                        **meta,
                        **extra,
                        "file_path": artifact.source_path,
                        "token_counter": embedding_tokenizer_name(),
                        **artifact.metadata,
                    },
                )
            )
    for c in chunks:
        c.total_chunks = len(chunks)
    return chunks


def _def_start(node: ast.AST) -> int:
    """First line of a definition, including its decorators."""
    decorators = getattr(node, "decorator_list", []) or []
    return min([node.lineno] + [d.lineno for d in decorators])


def _def_end(node: ast.AST, n_lines: int) -> int:
    return min(getattr(node, "end_lineno", None) or n_lines, n_lines)


class CodeAwareChunker(BaseChunker):
    """
    Code-aware chunker: AST symbol boundaries for Python, a token-bounded sliding window
    for other languages (plan §10.6: tree-sitter for other languages is still to come).
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
        self._splitter = _Splitter(max_tokens_per_chunk)

    @property
    def chunker_name(self) -> str:
        return "code_aware_ast_chunker"

    def _python_units(self, tree: ast.Module, lines: List[str]) -> Optional[List[Unit]]:
        n = len(lines)
        nodes = sorted(
            (nd for nd in tree.body if isinstance(nd, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))),
            key=_def_start,
        )
        if not nodes:
            return None
        base = {"language": "python"}
        units: List[Unit] = []
        cursor = 1
        for k, node in enumerate(nodes):
            start, end = _def_start(node), _def_end(node, n)
            if cursor < start:
                gap = "<module_preamble>" if k == 0 else "<module_code>"
                units.append((cursor, start - 1, {**base, "symbol_name": gap,
                                                  "chunk_type": "module_header" if k == 0 else "module_code"}))
            text = "\n".join(lines[start - 1: end])
            methods = [m for m in getattr(node, "body", []) if isinstance(m, (ast.FunctionDef, ast.AsyncFunctionDef))]
            if isinstance(node, ast.ClassDef) and methods and not self._splitter.fits(text):
                units.extend(self._class_units(node, methods, start, end, n, base))
            else:
                units.append((start, end, {**base, "symbol_name": node.name,
                                           "chunk_type": "class" if isinstance(node, ast.ClassDef) else "function"}))
            cursor = end + 1
        if cursor <= n:
            units.append((cursor, n, {**base, "symbol_name": "<module_trailer>", "chunk_type": "module_trailer"}))
        return units

    @staticmethod
    def _class_units(node: ast.ClassDef, methods: List[ast.AST], start: int, end: int, n: int,
                     base: Dict) -> List[Unit]:
        """Oversized class -> header, each method, and the class body between/after methods."""
        units: List[Unit] = []
        first = _def_start(methods[0])
        if start < first:
            units.append((start, first - 1, {**base, "symbol_name": f"{node.name}.<header>",
                                             "chunk_type": "class_header"}))
        cursor = first
        for m in methods:
            m_start, m_end = _def_start(m), _def_end(m, n)
            if cursor < m_start:
                units.append((cursor, m_start - 1, {**base, "symbol_name": f"{node.name}.<body>",
                                                    "chunk_type": "class_body"}))
            units.append((m_start, m_end, {**base, "symbol_name": f"{node.name}.{m.name}", "chunk_type": "method"}))
            cursor = m_end + 1
        if cursor <= end:
            units.append((cursor, end, {**base, "symbol_name": f"{node.name}.<body>", "chunk_type": "class_body"}))
        return units

    def chunk(self, artifact: BaseArtifact) -> List[KnowledgeChunk]:
        content = artifact.raw_content or ""
        lines = content.splitlines()
        if not lines:
            return []

        is_python = (
            (isinstance(artifact, SourceFile) and artifact.language == ProgrammingLanguage.PYTHON)
            or bool(artifact.source_path and artifact.source_path.endswith(".py"))
        )
        if is_python:
            try:
                units = self._python_units(ast.parse(content), lines)
            except (SyntaxError, ValueError):
                units = None
            if units:
                return _build_chunks(artifact, lines, units, self._splitter)

        # Non-Python (or unparsable) code: token-bounded sliding window with line overlap.
        window = [(1, len(lines), {"symbol_name": None, "chunk_type": "code_block"})]
        return _build_chunks(artifact, lines, window, self._splitter, overlap_lines=self.overlap_lines)


class DocAwareChunker(BaseChunker):
    """
    Heading-aware chunker for Markdown, RST, plain text and configuration files.
    """

    def __init__(
        self,
        max_tokens_per_chunk: int = 512,
        min_tokens_per_chunk: int = 15,
    ) -> None:
        self.max_tokens_per_chunk = max_tokens_per_chunk
        self.min_tokens_per_chunk = min_tokens_per_chunk
        self._splitter = _Splitter(max_tokens_per_chunk)

    @property
    def chunker_name(self) -> str:
        return "doc_aware_heading_chunker"

    @staticmethod
    def _sections(lines: List[str]) -> List[Tuple[str, int, int]]:
        """(title, start_line, end_line) per heading section (Markdown '#' or RST underline)."""
        heading_pattern = re.compile(r"^(#{1,6})\s+(.+)$")
        rst_heading_chars = set("=-~`#*^+\"':")
        sections: List[Tuple[str, int, int]] = []
        title, start = "Introduction", 1
        for i, line in enumerate(lines, start=1):
            m = heading_pattern.match(line)
            nxt = lines[i] if i < len(lines) else ""
            is_rst = bool(line.strip()) and len(nxt) >= 3 and all(c == nxt[0] for c in nxt) and nxt[0] in rst_heading_chars
            if (m or is_rst) and i > start:
                sections.append((title, start, i - 1))
            if m or is_rst:
                title, start = (m.group(2) if m else line.strip()), i
        sections.append((title, start, len(lines)))
        return sections

    @staticmethod
    def _paragraphs(start: int, end: int, lines: List[str]) -> List[Tuple[int, int]]:
        """Blank-line separated paragraphs of lines[start..end] as (first, last) line numbers."""
        paras, first = [], None
        for ln in range(start, end + 1):
            if lines[ln - 1].strip():
                first = ln if first is None else first
            elif first is not None:
                paras.append((first, ln - 1))
                first = None
        if first is not None:
            paras.append((first, end))
        return paras

    def chunk(self, artifact: BaseArtifact) -> List[KnowledgeChunk]:
        content = artifact.raw_content or ""
        lines = content.splitlines()
        if not lines:
            return []

        units: List[Unit] = []
        for title, start, end in self._sections(lines):
            text = "\n".join(lines[start - 1: end]).strip()
            if not text:
                continue
            if self._splitter.fits(text):
                units.append((start, end, {"section_title": title, "chunk_type": "doc_section"}))
                continue
            # Too long: pack whole paragraphs into blocks; a paragraph that is itself too
            # long becomes its own unit and is split by lines in _build_chunks.
            block: Optional[List[int]] = None
            for p_start, p_end in self._paragraphs(start, end, lines):
                candidate = (block[0] if block else p_start, p_end)
                if block and self._splitter.fits("\n".join(lines[candidate[0] - 1: candidate[1]])):
                    block[1] = p_end
                    continue
                if block:
                    units.append((block[0], block[1], {"section_title": title, "chunk_type": "doc_paragraph_block"}))
                block = [p_start, p_end]
            if block:
                units.append((block[0], block[1], {"section_title": title, "chunk_type": "doc_paragraph_block"}))
        return _build_chunks(artifact, lines, units, self._splitter)


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
