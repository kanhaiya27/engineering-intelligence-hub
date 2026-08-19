"""
Engineering Intelligence Hub — Research Failure Taxonomy (Phase-2 M5)
======================================================================
Defines 13 standard failure modes for software engineering RAG systems
and provides automated diagnostic classification over experimental traces.

Failure Categories:
  1. RETRIEVAL_MISS               : Zero or completely irrelevant chunks retrieved
  2. GRAPH_MISS                   : Graph expansion failed to retrieve required cross-file relations
  3. IRRELEVANT_EVIDENCE          : Evidence was retrieved but does not answer the question
  4. UNSUPPORTED_CITATION         : Answer cites files/lines absent from retrieved evidence
  5. HALLUCINATION                : Answer asserts facts contradictory to repository evidence
  6. QUALITY_GATE_FALSE_POSITIVE  : Quality gate passed an answer that contains factual errors
  7. QUALITY_GATE_FALSE_NEGATIVE  : Quality gate rejected a correct, grounded answer
  8. UNNECESSARY_ESCALATION       : Escalation triggered when Attempt 0 was already acceptable
  9. EXCESSIVE_LATENCY            : Pipeline latency exceeded acceptable operational threshold (>5000ms)
 10. EXCESSIVE_ENERGY             : Energy consumption > 3x Baseline B without proportional quality gain
 11. EXCESSIVE_COST               : Monetary cost > 3x Baseline B
 12. PARSER_FAILURE               : Extraction, chunking, or regex parsing error
 13. API_FAILURE                  : Network timeout or upstream LLM provider error
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field

from experiments.m5.metrics import TrialResult


class FailureCategory(str, Enum):
    """The 13 standard failure modes."""
    RETRIEVAL_MISS              = "retrieval_miss"
    GRAPH_MISS                  = "graph_miss"
    IRRELEVANT_EVIDENCE         = "irrelevant_evidence"
    UNSUPPORTED_CITATION        = "unsupported_citation"
    HALLUCINATION               = "hallucination"
    QUALITY_GATE_FALSE_POSITIVE = "quality_gate_false_positive"
    QUALITY_GATE_FALSE_NEGATIVE = "quality_gate_false_negative"
    UNNECESSARY_ESCALATION      = "unnecessary_escalation"
    EXCESSIVE_LATENCY           = "excessive_latency"
    EXCESSIVE_ENERGY            = "excessive_energy"
    EXCESSIVE_COST              = "excessive_cost"
    PARSER_FAILURE              = "parser_failure"
    API_FAILURE                 = "api_failure"
    NO_FAILURE                  = "no_failure"


class FailureDiagnosis(BaseModel):
    """Structured diagnostic record for an experimental run."""
    task_id: str
    system_id: str
    trial_index: int
    primary_failure: FailureCategory
    secondary_failures: List[FailureCategory] = Field(default_factory=list)
    diagnostic_details: str
    metadata: Dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(use_enum_values=True)


def diagnose_trial_failure(
    trial: TrialResult,
    baseline_b_energy: Optional[float] = None,
    baseline_b_cost: Optional[float] = None,
) -> FailureDiagnosis:
    """
    Diagnose primary and secondary failure categories from trial telemetry.
    """
    failures: List[FailureCategory] = []
    details: List[str] = []

    # 1. Retrieval & Graph Misses
    if trial.system_id != "baseline_a" and trial.chunks_retrieved_count == 0:
        failures.append(FailureCategory.RETRIEVAL_MISS)
        details.append("Zero chunks retrieved for RAG query.")

    if trial.system_id in ("system_d", "system_e") and trial.graph_chunks_count == 0:
        # If task was architecture/incident but graph injected 0 chunks
        if "arch" in trial.task_id or "dep" in trial.task_id:
            failures.append(FailureCategory.GRAPH_MISS)
            details.append("Graph augmentation failed to retrieve structural context.")

    # 2. Citation & Evidence Grounding Failures
    if trial.citation_validity_rate < 0.70 and "INSUFFICIENT EVIDENCE" not in trial.generated_answer:
        failures.append(FailureCategory.UNSUPPORTED_CITATION)
        details.append(f"Citation validity low: {trial.citation_validity_rate:.1%}.")

    if trial.consistency_score < 0.70:
        failures.append(FailureCategory.HALLUCINATION)
        details.append(f"Consistency score low: {trial.consistency_score:.2f}.")

    if trial.relevance_score < 0.50:
        failures.append(FailureCategory.IRRELEVANT_EVIDENCE)
        details.append(f"Relevance score low: {trial.relevance_score:.2f}.")

    # 3. Efficiency Failures
    if trial.latency_ms > 5000.0:
        failures.append(FailureCategory.EXCESSIVE_LATENCY)
        details.append(f"Latency {trial.latency_ms:.1f}ms exceeded 5000ms threshold.")

    if baseline_b_energy and trial.total_energy_joules > (baseline_b_energy * 3.0):
        failures.append(FailureCategory.EXCESSIVE_ENERGY)
        details.append(f"Energy {trial.total_energy_joules:.2f}J exceeded 3x Baseline B.")

    if baseline_b_cost and trial.cost_usd > (baseline_b_cost * 3.0):
        failures.append(FailureCategory.EXCESSIVE_COST)
        details.append(f"Cost ${trial.cost_usd:.6f} exceeded 3x Baseline B.")

    # 4. Quality Gate Failures
    if trial.system_id == "system_e":
        if not trial.passed_quality_gate and trial.correctness_score >= 0.85:
            failures.append(FailureCategory.QUALITY_GATE_FALSE_NEGATIVE)
            details.append("Quality gate rejected a highly correct answer.")
        elif trial.passed_quality_gate and trial.correctness_score < 0.50:
            failures.append(FailureCategory.QUALITY_GATE_FALSE_POSITIVE)
            details.append("Quality gate accepted an answer with low correctness.")
        elif trial.escalation_count > 0 and trial.correctness_score >= 0.90:
            # Check if attempt 0 was already above threshold
            details.append("Escalation triggered on high-quality task.")

    primary = failures[0] if failures else FailureCategory.NO_FAILURE
    secondary = failures[1:] if len(failures) > 1 else []

    return FailureDiagnosis(
        task_id=trial.task_id,
        system_id=trial.system_id,
        trial_index=trial.trial_index,
        primary_failure=primary,
        secondary_failures=secondary,
        diagnostic_details=" | ".join(details) if details else "Execution satisfied all quality and efficiency criteria.",
    )
