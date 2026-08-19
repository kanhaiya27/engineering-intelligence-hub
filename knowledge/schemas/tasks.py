"""
Engineering Intelligence Hub — Task / Query Schemas
====================================================
Models representing an engineering task request flowing through the system.

Pipeline:
  EngTaskRequest
      → TaskClassification (classifier output)
      → TaskComplexity
      → TaskCriticality
      → RetrievalStrategyConfig (in retrieval module)
      → EngTaskResponse (final output with quality + sustainability metadata)
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------


class SDLCStage(str, Enum):
    """Software Development Life Cycle stage."""

    REQUIREMENTS = "requirements"
    ARCHITECTURE = "architecture"
    DEVELOPMENT = "development"
    TESTING = "testing"
    CODE_REVIEW = "code_review"
    DEPLOYMENT = "deployment"
    OPERATIONS = "operations"
    MAINTENANCE = "maintenance"
    UNKNOWN = "unknown"


class TaskType(str, Enum):
    """
    Fine-grained task type within an SDLC stage.
    Initial supported set (Phase-0 definition); extend in Phase-1.
    """

    # Requirements
    REQUIREMENT_UNDERSTANDING = "requirement_understanding"
    REQUIREMENT_RETRIEVAL = "requirement_retrieval"

    # Architecture
    ARCHITECTURE_QA = "architecture_qa"
    DEPENDENCY_UNDERSTANDING = "dependency_understanding"
    ARCHITECTURE_DECISION_SUPPORT = "architecture_decision_support"

    # Development
    CODE_EXPLANATION = "code_explanation"
    CODE_GENERATION = "code_generation"
    REPOSITORY_ASSISTANCE = "repository_assistance"

    # Testing
    TEST_GENERATION = "test_generation"
    TEST_EXPLANATION = "test_explanation"
    TEST_FAILURE_ANALYSIS = "test_failure_analysis"

    # Code review
    DEFECT_DETECTION = "defect_detection"
    RISK_IDENTIFICATION = "risk_identification"
    REVIEW_ASSISTANCE = "review_assistance"

    # Deployment / change impact
    CHANGE_IMPACT_ANALYSIS = "change_impact_analysis"
    DEPENDENCY_ANALYSIS = "dependency_analysis"

    # Operations / incident
    ERROR_ANALYSIS = "error_analysis"
    INCIDENT_RETRIEVAL = "incident_retrieval"
    ROOT_CAUSE_ASSISTANCE = "root_cause_assistance"

    # Maintenance
    TECHNICAL_DEBT_ANALYSIS = "technical_debt_analysis"
    CHANGE_UNDERSTANDING = "change_understanding"
    HISTORICAL_REASONING = "historical_reasoning"

    UNKNOWN = "unknown"


class ComplexityLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    VERY_HIGH = "very_high"
    UNKNOWN = "unknown"


class CriticalityLevel(str, Enum):
    """
    Operational criticality of the task outcome.
    Higher criticality → stricter quality threshold, slower escalation path allowed.
    """

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"
    UNKNOWN = "unknown"


class SecuritySensitivity(str, Enum):
    NONE = "none"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    UNKNOWN = "unknown"


class TaskStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    ESCALATED = "escalated"
    FAILED = "failed"


# ---------------------------------------------------------------------------
# Task request
# ---------------------------------------------------------------------------


class EngTaskRequest(BaseModel):
    """
    An engineering task request submitted to the system.

    The user provides the query and optionally hints at the repository
    and SDLC stage. Classification fills in the remaining fields.
    """

    task_id: str = Field(description="Unique identifier for this request")
    query: str = Field(description="The user's engineering question or instruction")
    repository: Optional[str] = Field(
        default=None,
        description="Target repository (owner/repo) — used to scope retrieval",
    )
    sdlc_stage_hint: Optional[SDLCStage] = Field(
        default=None,
        description="Optional user hint for SDLC stage — overridden by classifier",
    )
    task_type_hint: Optional[TaskType] = Field(
        default=None,
        description="Optional user hint for task type",
    )
    context_files: List[str] = Field(
        default_factory=list,
        description="Optional list of file paths the user explicitly wants included",
    )
    quality_threshold_override: Optional[float] = Field(
        default=None,
        description="If set, overrides the task-type default quality threshold",
        ge=0.0,
        le=1.0,
    )
    experiment_id: Optional[str] = Field(
        default=None,
        description="Associate with an active experiment run for logging",
    )
    metadata: Dict[str, Any] = Field(default_factory=dict)

    class Config:
        use_enum_values = True


# ---------------------------------------------------------------------------
# Task classification output
# ---------------------------------------------------------------------------


class TaskClassification(BaseModel):
    """
    Output of the task classifier component.
    Drives retrieval strategy and model routing decisions.
    """

    task_id: str
    sdlc_stage: SDLCStage = Field(description="Classified SDLC stage")
    task_type: TaskType = Field(description="Classified task type")
    complexity: ComplexityLevel = Field(description="Estimated task complexity")
    criticality: CriticalityLevel = Field(description="Estimated operational criticality")
    security_sensitivity: SecuritySensitivity = Field(
        description="Estimated security sensitivity of the task"
    )
    quality_threshold: float = Field(
        description="Required minimum quality score (0.0–1.0) for this task",
        ge=0.0,
        le=1.0,
    )
    classifier_confidence: float = Field(
        description="Classifier's confidence in its own output (0.0–1.0)",
        ge=0.0,
        le=1.0,
        default=1.0,
    )
    reasoning: Optional[str] = Field(
        default=None,
        description="Human-readable explanation of classification decision",
    )

    class Config:
        use_enum_values = True


# ---------------------------------------------------------------------------
# Retrieved context
# ---------------------------------------------------------------------------


class RetrievedChunk(BaseModel):
    """A retrieved knowledge chunk with its relevance score."""

    chunk_id: str
    content: str
    score: float = Field(description="Relevance / similarity score (higher = more relevant)")
    artifact_id: Optional[str] = None
    artifact_type: Optional[str] = None
    repository: Optional[str] = None
    source_path: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class RetrievalResult(BaseModel):
    """Aggregated retrieval result for a single task."""

    task_id: str
    strategy_used: str = Field(description="Name of the retrieval strategy applied")
    chunks: List[RetrievedChunk] = Field(default_factory=list)
    total_retrieved: int = Field(default=0)
    retrieval_latency_ms: Optional[float] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Task response
# ---------------------------------------------------------------------------


class EngTaskResponse(BaseModel):
    """
    Final response to an engineering task request.

    Includes the generated answer plus quality and sustainability metadata
    for every downstream analysis step (experiment logging, Pareto analysis).
    """

    task_id: str
    status: TaskStatus = Field(default=TaskStatus.COMPLETED)
    answer: str = Field(description="Generated response text")

    # --- Classification ---
    classification: Optional[TaskClassification] = None

    # --- Retrieval ---
    retrieval: Optional[RetrievalResult] = None

    # --- Quality ---
    quality_score: Optional[float] = Field(
        default=None, description="Overall quality score (0.0–1.0)"
    )
    quality_threshold_used: Optional[float] = Field(
        default=None, description="The threshold that was applied"
    )
    passed_quality_gate: Optional[bool] = None
    escalation_count: int = Field(
        default=0, description="Number of escalations performed"
    )
    verification_details: Optional[Dict[str, Any]] = Field(
        default=None, description="Detailed quality signal breakdown"
    )

    # --- Generation ---
    model_id: Optional[str] = Field(
        default=None, description="Model used for final generation"
    )
    input_tokens: Optional[int] = None
    output_tokens: Optional[int] = None
    latency_ms: Optional[float] = None

    # --- Sustainability ---
    energy_joules: Optional[float] = Field(
        default=None,
        description="Estimated energy consumption in joules — see sustainability boundary docs",
    )
    cost_usd: Optional[float] = Field(
        default=None, description="Estimated monetary cost in USD"
    )
    co2e_grams: Optional[float] = Field(
        default=None,
        description="Estimated CO2-equivalent in grams — see sustainability boundary docs",
    )

    # --- Meta ---
    experiment_id: Optional[str] = None
    created_at: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)

    class Config:
        use_enum_values = True
