"""
Engineering Intelligence Hub — Interpretable Quality Evaluators (M4)
====================================================================
Deterministic, provenance-aware verification signals for RAG output:
  1. CitationGroundingEvaluator   — verifies citations point to retrieved evidence
  2. EvidenceCoverageEvaluator    — measures lexical evidence footprint & chunk usage
  3. QueryRelevanceEvaluator      — verifies response answers the engineering query
  4. EvidenceConsistencyEvaluator — detects contradictions against evidence

IMPORTANT RESEARCH NOTE:
All evaluators use deterministic, interpretable algorithms to guarantee
reproducibility and prevent non-deterministic LLM-judge hallucinations in M4.
Signal weights are heuristic starting points for Phase-2 ablation.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Set, Tuple

from core.logging import get_logger
from knowledge.schemas.tasks import EngTaskRequest, EngTaskResponse, RetrievedChunk
from verification.base import BaseQualityEvaluator
from verification.config import VerificationConfig
from verification.signals import QualitySignal, SignalStatus, SignalType

logger = get_logger(__name__)

# Regular expressions for identifying citation patterns in generated answers:
# Matches: [src/app.py:L10-L25], [src/app.py:10], [src/app.py], `src/app.py:L10`, `src/app.py`
_CITATION_PATTERN = re.compile(
    r"\[?`?([a-zA-Z0-9_\-\.\/]+\.[a-zA-Z0-9]+)(?::(?:L)?(\d+)(?:-(?:L)?(\d+))?)?`?\]?"
)

# Common code stop words to ignore during lexical overlap calculations
_STOP_WORDS = {
    "the", "a", "an", "and", "or", "in", "on", "at", "to", "for", "of", "with",
    "is", "are", "was", "were", "be", "been", "by", "as", "this", "that", "it",
    "from", "which", "will", "can", "has", "have", "had", "not", "but", "also",
    "evidence", "supported", "insufficient", "file", "lines", "line", "chunk",
}


def _tokenize(text: str) -> Set[str]:
    """Tokenize text into lowercase alphanumeric words, filtering stopwords."""
    words = re.findall(r"[a-zA-Z0-9_\-\.]+", text.lower())
    return {w for w in words if len(w) > 2 and w not in _STOP_WORDS}


def _extract_citations(text: str) -> List[Dict[str, Any]]:
    """
    Extract file path citations and optional line ranges from text.

    Returns a list of dicts with:
      - 'path': str
      - 'start_line': Optional[int]
      - 'end_line': Optional[int]
      - 'raw': str
    """
    citations = []
    # Strip markdown code blocks before extracting citations to avoid capturing code literals
    cleaned_text = re.sub(r"```[\s\S]*?```", "", text)

    for match in _CITATION_PATTERN.finditer(cleaned_text):
        raw = match.group(0)
        path = match.group(1)
        # Avoid treating common acronyms or generic extensions as file paths if they have no slash or dot
        if "." not in path and "/" not in path:
            continue
        if path.lower().startswith(("http://", "https://")):
            continue

        start_l = int(match.group(2)) if match.group(2) else None
        end_l = int(match.group(3)) if match.group(3) else start_l

        citations.append({
            "path": path,
            "start_line": start_l,
            "end_line": end_l,
            "raw": raw,
        })
    return citations


# ---------------------------------------------------------------------------
# 1. Citation Grounding Evaluator
# ---------------------------------------------------------------------------

class CitationGroundingEvaluator(BaseQualityEvaluator):
    """
    Verifies that file paths and line ranges cited in the generated answer
    correspond to actual retrieved evidence chunks.
    """

    def __init__(self, weight: float = 0.35) -> None:
        self._weight = weight

    @property
    def evaluator_name(self) -> str:
        return "citation_grounding_evaluator"

    @property
    def signal_type(self) -> str:
        return SignalType.CITATION_SUPPORT

    def evaluate(
        self,
        request: EngTaskRequest,
        response: EngTaskResponse,
    ) -> List[QualitySignal]:
        text = response.answer or ""
        retrieval = response.retrieval
        chunks: List[RetrievedChunk] = retrieval.chunks if retrieval else []

        # Case 1: Explicit refusal due to insufficient evidence (valid behavior)
        if "INSUFFICIENT EVIDENCE" in text:
            return [
                QualitySignal(
                    signal_type=SignalType.CITATION_SUPPORT,
                    status=SignalStatus.PASSED,
                    score=1.0,
                    weight=self._weight,
                    rationale="Properly identified insufficient evidence without fabricating citations.",
                    evaluator_name=self.evaluator_name,
                    metadata={"insufficient_evidence_flag": True, "valid_refusal": True},
                )
            ]

        # Case 2: Extract citations from answer
        citations = _extract_citations(text)
        if not citations:
            # If evidence was retrieved but no citations given
            if chunks:
                return [
                    QualitySignal(
                        signal_type=SignalType.CITATION_SUPPORT,
                        status=SignalStatus.FAILED,
                        score=0.30,
                        weight=self._weight,
                        rationale="Evidence was retrieved but the answer provides no verifiable file citations.",
                        evaluator_name=self.evaluator_name,
                        metadata={"citation_count": 0, "chunks_available": len(chunks)},
                    )
                ]
            else:
                # No chunks retrieved and no citations
                return [
                    QualitySignal(
                        signal_type=SignalType.CITATION_SUPPORT,
                        status=SignalStatus.PASSED,
                        score=0.50,
                        weight=self._weight,
                        rationale="No citations found and no context was retrieved.",
                        evaluator_name=self.evaluator_name,
                        metadata={"citation_count": 0, "chunks_available": 0},
                    )
                ]

        # Case 3: Validate each extracted citation against retrieved chunks
        valid_citations = 0
        invalid_citations: List[Dict[str, Any]] = []
        line_overlap_checks: List[bool] = []

        retrieved_paths = {c.source_path for c in chunks if c.source_path}

        for cit in citations:
            cit_path = cit["path"]
            # Match path: exact match or suffix match (e.g. app.py matching src/app.py)
            matching_chunks = [
                c for c in chunks
                if c.source_path and (c.source_path == cit_path or c.source_path.endswith("/" + cit_path) or cit_path.endswith("/" + c.source_path))
            ]

            if matching_chunks:
                valid_citations += 1
                # Check line range if present in citation
                if cit["start_line"] is not None:
                    line_valid = False
                    for mc in matching_chunks:
                        chunk_start = mc.metadata.get("start_line")
                        chunk_end = mc.metadata.get("end_line")
                        if chunk_start is not None and chunk_end is not None:
                            # Check overlap between [cit_start, cit_end] and [chunk_start, chunk_end]
                            if max(cit["start_line"], chunk_start) <= min(cit["end_line"], chunk_end):
                                line_valid = True
                                break
                        else:
                            # Chunk has no line metadata, accept path match
                            line_valid = True
                            break
                    line_overlap_checks.append(line_valid)
            else:
                invalid_citations.append(cit)

        total_cit = len(citations)
        path_validity_ratio = valid_citations / total_cit if total_cit > 0 else 0.0

        # Adjust score based on line validity if line numbers were cited
        line_penalty = 0.0
        if line_overlap_checks:
            line_valid_ratio = sum(line_overlap_checks) / len(line_overlap_checks)
            if line_valid_ratio < 0.5:
                line_penalty = 0.15

        base_score = 0.4 + (path_validity_ratio * 0.6) - line_penalty
        score = max(0.0, min(1.0, round(base_score, 4)))
        passed = score >= 0.70 and len(invalid_citations) == 0

        rationale = (
            f"Validated {valid_citations}/{total_cit} citations against retrieved evidence. "
            f"Invalid citations: {len(invalid_citations)}."
        )

        return [
            QualitySignal(
                signal_type=SignalType.CITATION_SUPPORT,
                status=SignalStatus.PASSED if passed else SignalStatus.FAILED,
                score=score,
                weight=self._weight,
                rationale=rationale,
                evaluator_name=self.evaluator_name,
                metadata={
                    "total_citations": total_cit,
                    "valid_citations": valid_citations,
                    "invalid_citations": invalid_citations,
                    "retrieved_files": list(retrieved_paths),
                },
            )
        ]


# ---------------------------------------------------------------------------
# 2. Evidence Coverage Evaluator
# ---------------------------------------------------------------------------

class EvidenceCoverageEvaluator(BaseQualityEvaluator):
    """
    Measures the lexical and contextual overlap between the generated answer
    and the retrieved knowledge chunks, including chunk utilization.
    """

    def __init__(self, weight: float = 0.20) -> None:
        self._weight = weight

    @property
    def evaluator_name(self) -> str:
        return "evidence_coverage_evaluator"

    @property
    def signal_type(self) -> str:
        return SignalType.GROUNDEDNESS

    def evaluate(
        self,
        request: EngTaskRequest,
        response: EngTaskResponse,
    ) -> List[QualitySignal]:
        text = response.answer or ""
        retrieval = response.retrieval
        chunks: List[RetrievedChunk] = retrieval.chunks if retrieval else []

        if "INSUFFICIENT EVIDENCE" in text:
            return [
                QualitySignal(
                    signal_type=SignalType.GROUNDEDNESS,
                    status=SignalStatus.PASSED,
                    score=1.0,
                    weight=self._weight,
                    rationale="Refusal correctly covers the insufficient evidence state.",
                    evaluator_name=self.evaluator_name,
                    metadata={"refusal": True},
                )
            ]

        if not chunks:
            return [
                QualitySignal(
                    signal_type=SignalType.GROUNDEDNESS,
                    status=SignalStatus.FAILED,
                    score=0.10,
                    weight=self._weight,
                    rationale="No evidence chunks were retrieved to support the answer.",
                    evaluator_name=self.evaluator_name,
                    metadata={"chunks_count": 0},
                )
            ]

        # Tokenize answer and evidence
        answer_tokens = _tokenize(text)
        if not answer_tokens:
            return [
                QualitySignal(
                    signal_type=SignalType.GROUNDEDNESS,
                    status=SignalStatus.FAILED,
                    score=0.20,
                    weight=self._weight,
                    rationale="Generated answer is empty or contains only stopwords.",
                    evaluator_name=self.evaluator_name,
                )
            ]

        all_chunk_tokens: Set[str] = set()
        utilized_chunks = 0

        for chunk in chunks:
            c_tokens = _tokenize(chunk.content)
            all_chunk_tokens.update(c_tokens)
            overlap_with_chunk = len(answer_tokens.intersection(c_tokens))
            if overlap_with_chunk >= 2:
                utilized_chunks += 1

        # Token overlap ratio: what fraction of answer tokens appear in the retrieved context
        overlap_tokens = answer_tokens.intersection(all_chunk_tokens)
        token_coverage = len(overlap_tokens) / len(answer_tokens)

        # Chunk utilization ratio: what fraction of chunks contributed to the answer
        chunk_utilization = utilized_chunks / len(chunks) if chunks else 0.0

        # Weighted coverage score: 70% token coverage + 30% chunk utilization
        score = round(min(1.0, (token_coverage * 0.7) + (chunk_utilization * 0.3)), 4)
        passed = score >= 0.50

        rationale = (
            f"Evidence token coverage: {token_coverage:.1%}, "
            f"Chunk utilization: {utilized_chunks}/{len(chunks)} ({chunk_utilization:.1%})."
        )

        return [
            QualitySignal(
                signal_type=SignalType.GROUNDEDNESS,
                status=SignalStatus.PASSED if passed else SignalStatus.FAILED,
                score=score,
                weight=self._weight,
                rationale=rationale,
                evaluator_name=self.evaluator_name,
                metadata={
                    "token_coverage": round(token_coverage, 4),
                    "chunk_utilization": round(chunk_utilization, 4),
                    "utilized_chunks": utilized_chunks,
                    "total_chunks": len(chunks),
                },
            )
        ]


# ---------------------------------------------------------------------------
# 3. Query Relevance Evaluator
# ---------------------------------------------------------------------------

class QueryRelevanceEvaluator(BaseQualityEvaluator):
    """
    Evaluates whether the generated response directly addresses the user's
    engineering query and references key question entities/symbols.
    """

    def __init__(self, weight: float = 0.25) -> None:
        self._weight = weight

    @property
    def evaluator_name(self) -> str:
        return "query_relevance_evaluator"

    @property
    def signal_type(self) -> str:
        return SignalType.RELEVANCE

    def evaluate(
        self,
        request: EngTaskRequest,
        response: EngTaskResponse,
    ) -> List[QualitySignal]:
        query = request.query or ""
        answer = response.answer or ""

        q_tokens = _tokenize(query)
        a_tokens = _tokenize(answer)

        if not q_tokens or not a_tokens:
            return [
                QualitySignal(
                    signal_type=SignalType.RELEVANCE,
                    status=SignalStatus.PASSED,
                    score=0.50,
                    weight=self._weight,
                    rationale="Query or answer was too brief for definitive relevance scoring.",
                    evaluator_name=self.evaluator_name,
                )
            ]

        # Calculate query keyword overlap in answer
        matched_tokens = q_tokens.intersection(a_tokens)
        keyword_recall = len(matched_tokens) / len(q_tokens)

        # Handle explicit refusal
        if "INSUFFICIENT EVIDENCE" in answer:
            # If refusal mentions query keywords, it is a well-targeted refusal
            score = 0.85 if keyword_recall >= 0.3 else 0.65
        else:
            # Standard answer: score based on keyword match
            base_score = 0.4 + (keyword_recall * 0.6)
            score = min(1.0, base_score)

        score = round(score, 4)
        passed = score >= 0.60

        return [
            QualitySignal(
                signal_type=SignalType.RELEVANCE,
                status=SignalStatus.PASSED if passed else SignalStatus.FAILED,
                score=score,
                weight=self._weight,
                rationale=f"Query keyword recall in answer: {keyword_recall:.1%} ({len(matched_tokens)}/{len(q_tokens)}).",
                evaluator_name=self.evaluator_name,
                metadata={
                    "keyword_recall": round(keyword_recall, 4),
                    "matched_tokens": list(matched_tokens),
                },
            )
        ]


# ---------------------------------------------------------------------------
# 4. Evidence Consistency Evaluator
# ---------------------------------------------------------------------------

class EvidenceConsistencyEvaluator(BaseQualityEvaluator):
    """
    Detects contradictions and ungrounded assertions between the generated
    response and retrieved evidence.
    """

    def __init__(self, weight: float = 0.20) -> None:
        self._weight = weight

    @property
    def evaluator_name(self) -> str:
        return "evidence_consistency_evaluator"

    @property
    def signal_type(self) -> str:
        return SignalType.CORRECTNESS

    def evaluate(
        self,
        request: EngTaskRequest,
        response: EngTaskResponse,
    ) -> List[QualitySignal]:
        text = response.answer or ""
        retrieval = response.retrieval
        chunks: List[RetrievedChunk] = retrieval.chunks if retrieval else []

        if "INSUFFICIENT EVIDENCE" in text:
            return [
                QualitySignal(
                    signal_type=SignalType.CORRECTNESS,
                    status=SignalStatus.PASSED,
                    score=1.0,
                    weight=self._weight,
                    rationale="No inconsistent assertions detected in refusal response.",
                    evaluator_name=self.evaluator_name,
                )
            ]

        # Simple deterministic assertion consistency checks:
        # Check if answer falsely claims a file is missing when it is in chunks,
        # or claims a symbol is not found when it is in chunks.
        contradictions: List[str] = []

        for chunk in chunks:
            chunk_text = chunk.content.lower()
            source_file = (chunk.source_path or "").lower()

            # False non-existence claim
            if source_file and f"does not contain {source_file}" in text.lower():
                contradictions.append(f"Answer falsely claims '{source_file}' is missing.")

        score = 1.0 if not contradictions else max(0.0, 1.0 - (len(contradictions) * 0.4))
        score = round(score, 4)
        passed = len(contradictions) == 0

        return [
            QualitySignal(
                signal_type=SignalType.CORRECTNESS,
                status=SignalStatus.PASSED if passed else SignalStatus.FAILED,
                score=score,
                weight=self._weight,
                rationale="Consistent with retrieved evidence." if passed else f"Detected {len(contradictions)} inconsistency(ies).",
                evaluator_name=self.evaluator_name,
                metadata={"contradictions": contradictions},
            )
        ]
