"""
EIH Pipeline Trace Contract — v1
================================
The frozen interface between the research pipeline (Laptop A) and the web
platform (Laptop B). Any change to this module, or to an enum it re-uses,
changes ``docs/api/openapi-v1.json`` and must go through a PR that both sides
review. Rules and field semantics: ``docs/API_CONTRACT.md``.

Design rules enforced here (not just documented):

- Every quantitative value is a ``Metric`` carrying a provenance tier
  (MEASURED / ESTIMATED / DERIVED). A value that was not obtained is ``null``
  with no tier — it is never filled with a default or a guess.
- Retrieval capabilities report ``requested`` and ``executed`` separately, so a
  configured-but-silent component (CLAUDE.md rule 4) is visible in every trace.
- Mock-LLM output can never be flagged as research evidence.
- No free-form ``Dict[str, Any]`` anywhere: every response field is typed and
  ``extra="forbid"``, so internal metadata (local paths, settings, secrets)
  cannot leak through a pass-through dict.
- File paths in citations must be repo-relative POSIX paths.
"""

from __future__ import annotations

import re
from datetime import datetime
from enum import Enum
from typing import Annotated, List, Literal, Optional, Union

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from knowledge.schemas.tasks import (
    ComplexityLevel,
    CriticalityLevel,
    SDLCStage,
    SecuritySensitivity,
    TaskType,
)
from retrieval.strategies import RerankerType, RetrievalMode
from verification.signals import SignalStatus, SignalType

CONTRACT_VERSION = "1.0.0"

QUERY_MAX_CHARS = 2000
CHUNK_CONTENT_MAX_CHARS = 4000

_REPO_PATTERN = r"^[A-Za-z0-9_.-]{1,100}/[A-Za-z0-9_.-]{1,100}$"
_MACHINE_ID_PATTERN = r"^[a-z0-9][a-z0-9-]{0,62}$"
_GIT_SHA_PATTERN = r"^([0-9a-f]{7,40}|unknown)$"
_WINDOWS_DRIVE = re.compile(r"^[A-Za-z]:")


class _ContractModel(BaseModel):
    """Base for every contract model: unknown fields are rejected server-side."""

    model_config = ConfigDict(extra="forbid")


# ---------------------------------------------------------------------------
# Provenance and metrics
# ---------------------------------------------------------------------------


class Provenance(str, Enum):
    """How a number was obtained (docs/PROJECT_REPORT.md §9.1)."""

    MEASURED = "MEASURED"    # directly observed: timers, token counters, NVML
    ESTIMATED = "ESTIMATED"  # documented method + assumptions: TDP proxy, CO2e, cost
    DERIVED = "DERIVED"      # computed from other values: weighted scores, ratios


MetricUnit = Literal["ms", "tokens", "usd", "joules", "gco2e", "score", "count"]


class Metric(_ContractModel):
    """A single number with its unit and provenance.

    ``value`` is ``null`` when the quantity was not obtained; then
    ``provenance`` is ``null`` and ``method`` is ``"not_available"``.
    """

    value: Optional[Union[int, float]] = Field(
        description="The number, or null if it was not obtained (never a placeholder)."
    )
    unit: MetricUnit
    provenance: Optional[Provenance] = Field(
        description="Provenance tier; null exactly when value is null."
    )
    method: str = Field(
        min_length=1,
        max_length=64,
        description=(
            "Machine-readable method id, e.g. perf_counter, provider_usage, "
            "nvml_power_sample, tdp_proxy, pricing_table, grid_intensity, "
            "weighted_mean, sum, not_available. Vocabulary: docs/API_CONTRACT.md §5."
        ),
    )
    note: Optional[str] = Field(default=None, max_length=300)

    @model_validator(mode="after")
    def _availability_consistent(self) -> "Metric":
        if self.value is None:
            if self.provenance is not None or self.method != "not_available":
                raise ValueError(
                    "an unavailable metric (value=null) must have provenance=null "
                    "and method='not_available'"
                )
        elif self.provenance is None:
            raise ValueError("an available metric must carry a provenance tier")
        return self


class ResourceMetrics(_ContractModel):
    """Resource accounting for one attempt, or totals for the whole trace.

    Totals inherit the weakest tier of their components (MEASURED is
    strongest); see docs/API_CONTRACT.md §5.
    """

    latency_ms: Metric
    input_tokens: Metric
    output_tokens: Metric
    cost_usd: Metric
    energy_joules: Metric = Field(description="cpu + gpu + rerank energy.")
    energy_cpu_joules: Metric
    energy_gpu_joules: Metric
    energy_rerank_joules: Metric
    co2e_grams: Metric


# ---------------------------------------------------------------------------
# Execution context (CLAUDE.md rule 5)
# ---------------------------------------------------------------------------


class SystemId(str, Enum):
    """Ablation ladder position (CLAUDE.md, 'What this project is')."""

    A = "A"  # LLM only, no retrieval
    B = "B"  # fixed hybrid RAG
    C = "C"  # + task-aware adaptive retrieval
    D = "D"  # + knowledge graph
    E = "E"  # + quality gate and bounded escalation


class GenerationSource(str, Enum):
    LIVE_MODEL = "live_model"  # a real model generated this answer during this request
    MOCK = "mock"              # MockLLMProvider — never research evidence
    CACHED_RUN = "cached_run"  # replayed from a stored run; see cached_from


class MachineInfo(_ContractModel):
    """The machine that PRODUCED the metrics (not necessarily the one serving)."""

    machine_id: str = Field(pattern=_MACHINE_ID_PATTERN, examples=["laptop-b"])
    gpu_name: Optional[str] = Field(default=None, max_length=120)
    torch_version: Optional[str] = Field(default=None, max_length=40)
    cuda_version: Optional[str] = Field(default=None, max_length=20)
    git_sha: str = Field(pattern=_GIT_SHA_PATTERN)
    carbon_region: str = Field(max_length=40, examples=["IN"])
    carbon_intensity_gco2_per_kwh: Optional[float] = Field(default=None, ge=0.0)


class CachedRunRef(_ContractModel):
    run_id: str = Field(max_length=120)
    recorded_at: datetime


class ExecutionContext(_ContractModel):
    producer: MachineInfo
    served_by_machine_id: str = Field(pattern=_MACHINE_ID_PATTERN)
    generation_source: GenerationSource
    research_evidence: bool = Field(
        description=(
            "True only if the answer came from a real model run. Always false for "
            "mock output. Does NOT mean the trace belongs to any benchmark."
        )
    )
    cached_from: Optional[CachedRunRef] = None

    @model_validator(mode="after")
    def _source_consistent(self) -> "ExecutionContext":
        if self.generation_source == GenerationSource.MOCK and self.research_evidence:
            raise ValueError("mock output can never be research evidence")
        if (self.generation_source == GenerationSource.CACHED_RUN) != (
            self.cached_from is not None
        ):
            raise ValueError("cached_from is required for, and only for, cached_run")
        return self


# ---------------------------------------------------------------------------
# Classification
# ---------------------------------------------------------------------------


class ClassificationTrace(_ContractModel):
    classifier: str = Field(max_length=64, examples=["rule_based"])
    sdlc_stage: SDLCStage
    task_type: TaskType
    task_type_source: Literal["classifier", "client_hint"]
    complexity: ComplexityLevel
    criticality: CriticalityLevel
    security_sensitivity: SecuritySensitivity
    quality_threshold: float = Field(ge=0.0, le=1.0)
    quality_threshold_source: Literal["classifier", "config_default"]
    classifier_confidence: float = Field(ge=0.0, le=1.0)
    reasoning: Optional[str] = Field(default=None, max_length=1000)
    latency_ms: Metric


# ---------------------------------------------------------------------------
# Retrieval
# ---------------------------------------------------------------------------


class RetrievedChunkTrace(_ContractModel):
    """One retrieved chunk with a file:line citation.

    ``content`` is UNTRUSTED repository text. Clients must render it as plain
    text (never HTML/Markdown with live links) and must never treat it as
    instructions. See docs/API_CONTRACT.md §6.
    """

    rank: int = Field(ge=1)
    chunk_id: str = Field(max_length=300)
    channel: Literal["dense", "sparse", "hybrid", "graph"] = Field(
        description="Which retrieval channel produced this chunk."
    )
    repository: Optional[str] = Field(default=None, pattern=_REPO_PATTERN)
    file_path: Optional[str] = Field(
        default=None, max_length=400, description="Repo-relative POSIX path."
    )
    start_line: Optional[int] = Field(default=None, ge=1)
    end_line: Optional[int] = Field(default=None, ge=1)
    symbol_name: Optional[str] = Field(default=None, max_length=200)
    commit_sha: Optional[str] = Field(default=None, pattern=r"^[0-9a-f]{7,40}$")
    citation: str = Field(
        max_length=800,
        description="'<repository>:<file_path>:<start_line>-<end_line>'; line part "
        "omitted when lines are unknown.",
        examples=["pallets/flask:src/flask/app.py:120-168"],
    )
    score: float
    score_kind: Literal["dense", "sparse", "fused", "rerank", "graph"]
    dense_score: Optional[float] = None
    sparse_score: Optional[float] = None
    pre_rerank_score: Optional[float] = None
    pre_rerank_rank: Optional[int] = Field(default=None, ge=1)
    graph_hop: Optional[int] = Field(default=None, ge=0)
    content: str = Field(max_length=CHUNK_CONTENT_MAX_CHARS)
    content_truncated: bool
    content_trust: Literal["untrusted"] = "untrusted"

    @field_validator("file_path")
    @classmethod
    def _repo_relative(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        if (
            v.startswith(("/", "~"))
            or "\\" in v
            or _WINDOWS_DRIVE.match(v)
            or ".." in v.split("/")
        ):
            raise ValueError("file_path must be a repo-relative POSIX path")
        return v

    @model_validator(mode="after")
    def _lines_and_citation(self) -> "RetrievedChunkTrace":
        if (self.start_line is None) != (self.end_line is None):
            raise ValueError("start_line and end_line must both be set or both null")
        if self.start_line is not None and self.end_line < self.start_line:
            raise ValueError("end_line must be >= start_line")
        if self.repository and self.file_path:
            expected = f"{self.repository}:{self.file_path}"
            if self.start_line is not None:
                expected += f":{self.start_line}-{self.end_line}"
            if self.citation != expected:
                raise ValueError(f"citation must be '{expected}'")
        return self


class ChannelExecution(_ContractModel):
    """Whether a retrieval channel was asked for, and whether it actually ran."""

    requested: bool
    executed: bool = Field(
        description="True only if runtime evidence shows the channel ran and "
        "returned a result set (possibly empty)."
    )
    candidates: Optional[int] = Field(default=None, ge=0)
    skip_reason: Optional[str] = Field(default=None, max_length=200)

    @model_validator(mode="after")
    def _executed_implies_requested(self):
        if self.executed and not self.requested:
            raise ValueError("a channel cannot execute without being requested")
        return self


class GraphExecution(ChannelExecution):
    hop_depth: Optional[int] = Field(default=None, ge=0)
    nodes_visited: Optional[int] = Field(default=None, ge=0)
    chunks_injected: Optional[int] = Field(default=None, ge=0)


class RerankerExecution(ChannelExecution):
    reranker_type: RerankerType
    returned: Optional[int] = Field(default=None, ge=0)
    latency_ms: Metric
    energy_joules: Metric


class RetrievalTrace(_ContractModel):
    """Retrieval for one attempt. All parameters describe what EXECUTED."""

    attempt_index: int = Field(ge=0)
    requested_strategy: str = Field(
        max_length=120,
        description="Strategy the policy or escalation asked for.",
    )
    strategy_name: str = Field(
        max_length=120,
        description="Strategy that actually executed. Differs from "
        "requested_strategy when the retriever fell back (see strategy_fallback).",
    )
    strategy_fallback: bool = Field(
        description="True if the executed strategy is not the requested one."
    )
    mode: RetrievalMode
    top_k: int = Field(ge=0)
    score_threshold: float
    dense_weight: Optional[float] = Field(default=None, ge=0.0)
    sparse_weight: Optional[float] = Field(default=None, ge=0.0)
    dense: ChannelExecution
    sparse: ChannelExecution
    graph: GraphExecution
    reranker: RerankerExecution
    chunks: List[RetrievedChunkTrace]
    latency_ms: Metric

    @model_validator(mode="after")
    def _ranks_and_fallback(self) -> "RetrievalTrace":
        if [c.rank for c in self.chunks] != list(range(1, len(self.chunks) + 1)):
            raise ValueError("chunk ranks must be 1..n in order")
        if self.strategy_fallback != (self.requested_strategy != self.strategy_name):
            raise ValueError("strategy_fallback must equal requested_strategy != strategy_name")
        return self


# ---------------------------------------------------------------------------
# Generation
# ---------------------------------------------------------------------------


class GenerationTrace(_ContractModel):
    attempt_index: int = Field(ge=0)
    provider: str = Field(max_length=40, examples=["ollama", "openai", "mock"])
    model_id: str = Field(max_length=120)
    is_local_model: bool
    finish_reason: Optional[Literal["stop", "length", "content_filter", "error"]] = None
    answer: str = Field(description="Raw model output for this attempt (untrusted text).")
    input_tokens: Metric
    output_tokens: Metric
    latency_ms: Metric


# ---------------------------------------------------------------------------
# Verification and escalation
# ---------------------------------------------------------------------------


class SignalTrace(_ContractModel):
    signal_type: SignalType
    evaluator_name: Optional[str] = Field(default=None, max_length=80)
    status: SignalStatus
    score: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    weight: float = Field(ge=0.0)
    provenance: Optional[Provenance] = Field(
        description="Tier of the score; null exactly when score is null."
    )
    rationale: Optional[str] = Field(default=None, max_length=1000)

    @model_validator(mode="after")
    def _provenance_matches_score(self) -> "SignalTrace":
        if (self.score is None) != (self.provenance is None):
            raise ValueError("provenance must be set exactly when score is set")
        return self


class VerificationTrace(_ContractModel):
    attempt_index: int = Field(ge=0)
    executed: bool = Field(description="False for systems A–D (no gate).")
    gate: Optional[str] = Field(default=None, max_length=64)
    threshold: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    aggregated_score: Metric
    passed: Optional[bool] = Field(description="null when the gate did not execute.")
    critical_failures: List[SignalType] = Field(default_factory=list)
    evaluator_errors: List[SignalType] = Field(default_factory=list)
    signals: List[SignalTrace] = Field(default_factory=list)

    @model_validator(mode="after")
    def _executed_consistent(self) -> "VerificationTrace":
        if self.executed and (self.passed is None or self.threshold is None):
            raise ValueError("an executed gate must report passed and threshold")
        if not self.executed and (self.passed is not None or self.signals):
            raise ValueError("a gate that did not execute cannot report results")
        return self


ParameterValue = Union[bool, int, float, str, None]


class ParameterChange(_ContractModel):
    name: str = Field(max_length=64, examples=["top_k"])
    before: ParameterValue
    after: ParameterValue


class EscalationStep(_ContractModel):
    from_attempt: int = Field(ge=0)
    to_attempt: int = Field(ge=1)
    rung: str = Field(
        max_length=64,
        description="Ladder rung id, e.g. expanded_retrieval, graph_augmentation, "
        "max_capability. The ladder length is configurable.",
    )
    from_strategy: str = Field(max_length=120)
    to_strategy: str = Field(max_length=120)
    trigger_score: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    threshold: float = Field(ge=0.0, le=1.0)
    critical_failures: List[SignalType] = Field(default_factory=list)
    changes: List[ParameterChange] = Field(default_factory=list)

    @model_validator(mode="after")
    def _consecutive(self) -> "EscalationStep":
        if self.to_attempt != self.from_attempt + 1:
            raise ValueError("escalation steps go from attempt n to n+1")
        return self


class EscalationSummary(_ContractModel):
    max_escalations: int = Field(ge=0)
    steps: List[EscalationStep] = Field(default_factory=list)
    exhausted: bool = Field(description="True if every allowed escalation failed.")


# ---------------------------------------------------------------------------
# Attempts, outcome, full trace
# ---------------------------------------------------------------------------


class AttemptTrace(_ContractModel):
    attempt_index: int = Field(ge=0)
    retrieval: Optional[RetrievalTrace] = Field(description="null for system A.")
    generation: GenerationTrace
    verification: VerificationTrace
    resources: ResourceMetrics

    @model_validator(mode="after")
    def _indices_match(self) -> "AttemptTrace":
        idx = {self.generation.attempt_index, self.verification.attempt_index}
        if self.retrieval is not None:
            idx.add(self.retrieval.attempt_index)
        if idx != {self.attempt_index}:
            raise ValueError("all parts of an attempt must share its attempt_index")
        return self


class Verdict(str, Enum):
    VERIFIED = "VERIFIED"                            # gate passed
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"  # gate failed on every allowed attempt
    UNVERIFIED = "UNVERIFIED"                        # no gate ran (systems A–D)
    ERROR = "ERROR"                                  # pipeline failed; see warnings


class Outcome(_ContractModel):
    verdict: Verdict
    answer: str = Field(
        description="Final answer, or the INSUFFICIENT EVIDENCE refusal text."
    )
    answer_attempt_index: Optional[int] = Field(
        default=None, ge=0, description="Attempt whose answer is returned; null on refusal."
    )


class PipelineTrace(_ContractModel):
    """The full trace of one query through the EIH pipeline."""

    contract_version: Literal["1.0.0"] = CONTRACT_VERSION
    trace_id: str = Field(max_length=64)
    request_id: str = Field(max_length=64)
    created_at: datetime
    query: str = Field(max_length=QUERY_MAX_CHARS)
    system: SystemId
    execution: ExecutionContext
    classification: Optional[ClassificationTrace] = Field(
        description="null if the system does not classify (A, B)."
    )
    attempts: List[AttemptTrace] = Field(min_length=1)
    escalation: EscalationSummary
    outcome: Outcome
    totals: ResourceMetrics
    warnings: List[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _trace_consistent(self) -> "PipelineTrace":
        n = len(self.attempts)
        if [a.attempt_index for a in self.attempts] != list(range(n)):
            raise ValueError("attempt indices must be 0..n-1 in order")
        if len(self.escalation.steps) != n - 1:
            raise ValueError("there must be exactly one escalation step between attempts")
        if n - 1 > self.escalation.max_escalations:
            raise ValueError("more escalations than max_escalations")
        if self.system == SystemId.A and any(a.retrieval for a in self.attempts):
            raise ValueError("system A performs no retrieval")
        if self.system != SystemId.A and any(a.retrieval is None for a in self.attempts):
            raise ValueError("systems B–E must report retrieval for every attempt")
        gate_ran = self.system == SystemId.E
        if any(a.verification.executed != gate_ran for a in self.attempts):
            raise ValueError("the quality gate runs for system E and only system E")
        if not gate_ran and n != 1:
            raise ValueError("systems A–D make exactly one attempt (no escalation)")

        last = self.attempts[-1].verification
        verdict = self.outcome.verdict
        if verdict == Verdict.VERIFIED and not (gate_ran and last.passed):
            raise ValueError("VERIFIED requires a passing gate on the last attempt")
        if verdict == Verdict.INSUFFICIENT_EVIDENCE and not (
            gate_ran and last.passed is False and self.escalation.exhausted
        ):
            raise ValueError("INSUFFICIENT_EVIDENCE requires exhausted, failing escalation")
        if verdict == Verdict.UNVERIFIED and gate_ran:
            raise ValueError("UNVERIFIED is only valid when no gate ran")
        return self


# ---------------------------------------------------------------------------
# Request and error bodies
# ---------------------------------------------------------------------------


class TraceRequest(_ContractModel):
    query: str = Field(min_length=3, max_length=QUERY_MAX_CHARS)
    repository: Optional[str] = Field(
        default=None,
        pattern=_REPO_PATTERN,
        description="Restrict retrieval to one ingested repository (owner/name).",
    )
    system: SystemId = SystemId.E
    task_type_hint: Optional[TaskType] = None


class ErrorCode(str, Enum):
    INVALID_REQUEST = "invalid_request"
    PAYLOAD_TOO_LARGE = "payload_too_large"
    RATE_LIMITED = "rate_limited"
    PIPELINE_UNAVAILABLE = "pipeline_unavailable"
    INTERNAL_ERROR = "internal_error"


class ErrorBody(_ContractModel):
    code: ErrorCode
    message: str = Field(
        max_length=500,
        description="Human-readable; never contains stack traces, paths or config.",
    )
    retry_after_s: Optional[int] = Field(default=None, ge=0)


class ErrorResponse(_ContractModel):
    contract_version: Literal["1.0.0"] = CONTRACT_VERSION
    request_id: str = Field(max_length=64)
    error: ErrorBody


# ---------------------------------------------------------------------------
# Streaming events (Server-Sent Events, POST /v1/trace/stream)
# ---------------------------------------------------------------------------


class _EventBase(_ContractModel):
    contract_version: Literal["1.0.0"] = CONTRACT_VERSION
    trace_id: str = Field(max_length=64)
    seq: int = Field(ge=0, description="0, 1, 2, … within one stream.")


class TraceStartedPayload(_ContractModel):
    request_id: str = Field(max_length=64)
    system: SystemId
    execution: ExecutionContext


class GenerationDeltaPayload(_ContractModel):
    attempt_index: int = Field(ge=0)
    text: str


class TraceStartedEvent(_EventBase):
    event: Literal["trace.started"] = "trace.started"
    payload: TraceStartedPayload


class ClassificationEvent(_EventBase):
    event: Literal["classification"] = "classification"
    payload: ClassificationTrace


class RetrievalEvent(_EventBase):
    event: Literal["retrieval"] = "retrieval"
    payload: RetrievalTrace


class GenerationDeltaEvent(_EventBase):
    event: Literal["generation.delta"] = "generation.delta"
    payload: GenerationDeltaPayload


class GenerationEvent(_EventBase):
    event: Literal["generation"] = "generation"
    payload: GenerationTrace


class VerificationEvent(_EventBase):
    event: Literal["verification"] = "verification"
    payload: VerificationTrace


class EscalationEvent(_EventBase):
    event: Literal["escalation"] = "escalation"
    payload: EscalationStep


class TraceCompletedEvent(_EventBase):
    event: Literal["trace.completed"] = "trace.completed"
    payload: PipelineTrace


class ErrorEvent(_EventBase):
    event: Literal["error"] = "error"
    payload: ErrorBody


TraceEvent = Annotated[
    Union[
        TraceStartedEvent,
        ClassificationEvent,
        RetrievalEvent,
        GenerationDeltaEvent,
        GenerationEvent,
        VerificationEvent,
        EscalationEvent,
        TraceCompletedEvent,
        ErrorEvent,
    ],
    Field(discriminator="event"),
]
