"""
Engineering Intelligence Hub — Custom Exception Hierarchy
==========================================================
All exceptions raised by EIH components derive from EIHException.
This makes it straightforward to catch all system errors at API boundaries
while still allowing fine-grained handling internally.
"""

from __future__ import annotations


class EIHException(Exception):
    """Base exception for all Engineering Intelligence Hub errors."""

    def __init__(self, message: str, details: str = "") -> None:
        self.message = message
        self.details = details
        super().__init__(message)

    def __repr__(self) -> str:  # pragma: no cover
        return f"{self.__class__.__name__}(message={self.message!r}, details={self.details!r})"


# ---------------------------------------------------------------------------
# Ingestion
# ---------------------------------------------------------------------------


class IngestionError(EIHException):
    """Raised when the ingestion pipeline fails to load or process a source."""


class UnsupportedSourceTypeError(IngestionError):
    """Raised when the requested source type has no registered loader."""


# ---------------------------------------------------------------------------
# Knowledge Store
# ---------------------------------------------------------------------------


class VectorStoreError(EIHException):
    """Raised when vector store operations fail (insert, query, delete)."""


class GraphStoreError(EIHException):
    """Raised when graph store operations fail."""


# ---------------------------------------------------------------------------
# Retrieval
# ---------------------------------------------------------------------------


class RetrievalError(EIHException):
    """Raised when retrieval fails or returns zero results unexpectedly."""


class InvalidRetrievalStrategyError(RetrievalError):
    """Raised when a named retrieval strategy is not found in the registry."""


# ---------------------------------------------------------------------------
# Routing / Generation
# ---------------------------------------------------------------------------


class RoutingError(EIHException):
    """Raised when no suitable model can be selected for the task."""


class GenerationError(EIHException):
    """Raised when the LLM provider fails to produce a response."""


class ProviderAuthenticationError(GenerationError):
    """Raised when the LLM provider rejects the API credentials."""


class ProviderRateLimitError(GenerationError):
    """Raised when the provider signals rate limiting."""


class ProviderTimeoutError(GenerationError):
    """Raised when the provider request exceeds the configured timeout."""


# ---------------------------------------------------------------------------
# Verification / Quality Gate
# ---------------------------------------------------------------------------


class QualityGateError(EIHException):
    """Raised when the quality gate itself encounters an internal failure."""


class EscalationExhaustedError(QualityGateError):
    """Raised when all escalation attempts are exhausted and quality is still below threshold."""


# ---------------------------------------------------------------------------
# Sustainability
# ---------------------------------------------------------------------------


class SustainabilityError(EIHException):
    """Raised when resource measurement or estimation fails."""


# ---------------------------------------------------------------------------
# Evaluation
# ---------------------------------------------------------------------------


class EvaluationError(EIHException):
    """Raised when an evaluator cannot score a response."""


class MissingGroundTruthError(EvaluationError):
    """Raised when evaluation is attempted without a ground-truth reference."""


# ---------------------------------------------------------------------------
# Experiment
# ---------------------------------------------------------------------------


class ExperimentError(EIHException):
    """Raised when experiment configuration or execution encounters an error."""


class DuplicateExperimentError(ExperimentError):
    """Raised when an experiment with the same ID already exists in the log."""


# ---------------------------------------------------------------------------
# Benchmark
# ---------------------------------------------------------------------------


class BenchmarkError(EIHException):
    """Raised for benchmark pipeline errors (generation, validation, export)."""


class InvalidBenchmarkTaskError(BenchmarkError):
    """Raised when a benchmark task fails schema or quality validation."""
