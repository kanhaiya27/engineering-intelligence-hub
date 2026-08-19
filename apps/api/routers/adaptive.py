"""
FastAPI Router — Adaptive Retrieval (Phase-2 M3)
================================================
Exposes task-aware adaptive retrieval endpoints.
Phase-1 /retrieve endpoint is UNCHANGED.

New endpoints:
  POST /adaptive/retrieve   — Full adaptive retrieval with task classification
  GET  /adaptive/strategies — List available strategies and policy map
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from core.logging import get_logger
from knowledge.schemas.tasks import EngTaskRequest, RetrievalResult, TaskClassification, TaskType

if TYPE_CHECKING:
    from intelligence.classifier import RuleBasedTaskClassifier
    from retrieval.adaptive import AdaptiveRetrievalPipeline, ExperimentMode

logger = get_logger(__name__)

router = APIRouter(prefix="/adaptive", tags=["Adaptive Retrieval (M3)"])

# Module-level singletons — created lazily on first request
_pipeline: Optional[Any] = None
_classifier: Optional[Any] = None


def _get_pipeline():
    global _pipeline
    if _pipeline is None:
        from retrieval.adaptive import AdaptiveRetrievalPipeline
        _pipeline = AdaptiveRetrievalPipeline(graph_store=None)
    return _pipeline


def _get_classifier():
    global _classifier
    if _classifier is None:
        from intelligence.classifier import RuleBasedTaskClassifier
        _classifier = RuleBasedTaskClassifier()
    return _classifier


# ---------------------------------------------------------------------------
# Request / Response schemas
# ---------------------------------------------------------------------------

class AdaptiveRetrieveRequest(BaseModel):
    """Request body for task-aware adaptive retrieval."""
    query: str = Field(description="Engineering query or task description")
    repository: Optional[str] = Field(default=None, description="Filter by repository name")
    task_type: Optional[str] = Field(
        default=None,
        description=(
            "Optional explicit task_type override. "
            "If omitted, task_type is inferred by the M1 classifier."
        ),
    )
    experiment_mode: str = Field(
        default="system_d",
        description=(
            "Experiment mode: 'baseline_b' (fixed hybrid), "
            "'system_c' (task-aware, no graph), "
            "'system_d' (task-aware + graph). "
            "Default: system_d."
        ),
    )
    override_strategy: Optional[str] = Field(
        default=None,
        description="Force a specific named strategy (ablation experiments only).",
    )
    task_id: Optional[str] = Field(default=None, description="Optional task tracking ID")


class AdaptiveRetrieveResponse(BaseModel):
    """Response from adaptive retrieval."""
    retrieval: RetrievalResult
    classification: TaskClassification
    resolved_strategy: Optional[str] = None
    experiment_mode: str


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post("/retrieve", response_model=AdaptiveRetrieveResponse)
async def adaptive_retrieve(req: AdaptiveRetrieveRequest):
    """
    Execute task-aware adaptive retrieval.

    1. Classify the query using M1 TaskClassifier
    2. Resolve the appropriate retrieval strategy via M3 AdaptiveRetrievalPolicy
    3. Execute retrieval (dense / hybrid / graph-augmented)
    4. Return chunks + classification metadata for research tracing
    """
    try:
        classifier = _get_classifier()
        pipeline = _get_pipeline()

        # 1. Classify the task
        task_id = req.task_id or f"api-adaptive-{id(req)}"
        eng_request = EngTaskRequest(
            query=req.query,
            repository=req.repository,
            task_id=task_id,
        )
        classification: TaskClassification = classifier.classify(eng_request)

        # 2. Optional task_type override (e.g. from benchmark harness)
        if req.task_type:
            try:
                task_type_val = TaskType(req.task_type)
                # Rebuild classification with override — preserve all other fields
                classification = TaskClassification(
                    task_id=classification.task_id,
                    task_type=task_type_val,
                    sdlc_stage=classification.sdlc_stage,
                    complexity=classification.complexity,
                    criticality=classification.criticality,
                    security_sensitivity=classification.security_sensitivity,
                    quality_threshold=classification.quality_threshold,
                    classifier_confidence=classification.classifier_confidence,
                    reasoning=classification.reasoning,
                )
            except ValueError:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Unknown task_type: '{req.task_type}'. Valid values: {[t.value for t in TaskType]}",
                )

        # 3. Validate experiment mode
        from retrieval.adaptive import ExperimentMode
        try:
            mode = ExperimentMode(req.experiment_mode)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Unknown experiment_mode: '{req.experiment_mode}'. Valid: {[m.value for m in ExperimentMode]}",
            )

        # 4. Execute adaptive retrieval
        result = pipeline.retrieve(
            query=req.query,
            classification=classification,
            experiment_mode=mode,
            override_strategy_name=req.override_strategy,
            task_id=task_id,
        )

        return AdaptiveRetrieveResponse(
            retrieval=result,
            classification=classification,
            resolved_strategy=result.metadata.get("resolved_strategy"),
            experiment_mode=mode.value,
        )

    except HTTPException:
        raise
    except Exception as exc:
        logger.error(f"Adaptive retrieval failed: {exc}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(exc),
        )


@router.get("/strategies", response_model=Dict[str, Any])
async def list_adaptive_strategies():
    """
    List the M3 strategy registry and task_type → strategy policy map.
    For research transparency and experiment planning.
    """
    try:
        from retrieval.policy import _CRITICALITY_OVERRIDE_MAP, _TASK_TYPE_STRATEGY_MAP
        pipeline = _get_pipeline()
        strategies = pipeline.list_strategies()

        return {
            "strategy_registry": {
                name: {
                    "mode": cfg.mode,
                    "top_k": cfg.top_k,
                    "dense_weight": cfg.dense_weight,
                    "sparse_weight": cfg.sparse_weight,
                    "include_graph_context": cfg.include_graph_context,
                    "graph_hop_depth": cfg.graph_hop_depth,
                    "enable_reranking": cfg.enable_reranking,
                }
                for name, cfg in strategies.items()
            },
            "task_type_policy": _TASK_TYPE_STRATEGY_MAP,
            "criticality_override_policy": _CRITICALITY_OVERRIDE_MAP,
            "experiment_modes": ["baseline_b", "system_c", "system_d", "system_e"],
            "note": (
                "All policy mappings are initial heuristic configurations. "
                "They will be validated and tuned in Phase-2 M5 controlled evaluation."
            ),
        }
    except Exception as exc:
        logger.error(f"Failed to list strategies: {exc}")
        raise HTTPException(status_code=500, detail=str(exc))


# ---------------------------------------------------------------------------
# M4 Quality-Aware Query Endpoints
# ---------------------------------------------------------------------------

class QualityQueryRequest(BaseModel):
    """Request for quality-gated engineering RAG query."""
    query: str = Field(description="Engineering query or task description")
    repository: Optional[str] = Field(default=None, description="Repository filter")
    task_type: Optional[str] = Field(default=None, description="Optional task type override")
    quality_threshold_override: Optional[float] = Field(
        default=None,
        description="Override task-specific quality threshold (0.0–1.0)",
    )
    experiment_mode: str = Field(
        default="system_d",
        description="Experiment mode (baseline_b, system_c, system_d)",
    )
    task_id: Optional[str] = Field(default=None, description="Tracking task ID")
    skip_verification: bool = Field(default=False, description="Skip quality gate (ablation)")


@router.post("/query")
async def quality_aware_query(req: QualityQueryRequest):
    """
    Execute full quality-gated engineering RAG pipeline.

    1. Classify task (M1)
    2. Adaptive retrieval (M3)
    3. LLM generation
    4. Quality verification (M4)
    5. Bounded escalation on failure -> Return verified answer or INSUFFICIENT EVIDENCE
    """
    try:
        from generation.quality_rag import QualityAwareRAGPipeline
        from retrieval.adaptive import ExperimentMode

        classifier = _get_classifier()
        task_id = req.task_id or f"api-quality-{id(req)}"

        # 1. Classify
        eng_req = EngTaskRequest(
            task_id=task_id,
            query=req.query,
            repository=req.repository,
            quality_threshold_override=req.quality_threshold_override,
        )
        classification = classifier.classify(eng_req)

        if req.task_type:
            try:
                task_type_val = TaskType(req.task_type)
                classification = TaskClassification(
                    task_id=classification.task_id,
                    task_type=task_type_val,
                    sdlc_stage=classification.sdlc_stage,
                    complexity=classification.complexity,
                    criticality=classification.criticality,
                    security_sensitivity=classification.security_sensitivity,
                    quality_threshold=classification.quality_threshold,
                    classifier_confidence=classification.classifier_confidence,
                    reasoning=classification.reasoning,
                )
            except ValueError:
                raise HTTPException(
                    status_code=400,
                    detail=f"Unknown task_type: '{req.task_type}'",
                )

        try:
            mode = ExperimentMode(req.experiment_mode)
        except ValueError:
            mode = ExperimentMode.SYSTEM_D

        # 2. Execute QualityAwareRAGPipeline
        pipeline = QualityAwareRAGPipeline(adaptive_pipeline=_get_pipeline())
        response = pipeline.execute(
            request=eng_req,
            classification=classification,
            experiment_mode=mode,
            skip_verification=req.skip_verification,
        )
        return response

    except HTTPException:
        raise
    except Exception as exc:
        logger.error(f"Quality query failed: {exc}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(exc),
        )


@router.post("/verify", response_model=Dict[str, Any])
async def verify_response_endpoint(req: Dict[str, Any]):
    """
    Run quality gate verification on an existing response and evidence.
    """
    try:
        from verification.gate import QualityGate
        from knowledge.schemas.tasks import EngTaskResponse

        task_id = req.get("task_id", "adhoc-verify")
        query = req.get("query", "")
        answer = req.get("answer", "")
        threshold = req.get("threshold", 0.75)
        chunks = req.get("chunks", [])

        eng_req = EngTaskRequest(task_id=task_id, query=query)
        retrieval_res = RetrievalResult(
            task_id=task_id,
            strategy_used="verify_payload",
            chunks=[RetrievedChunk(**c) for c in chunks],
            total_retrieved=len(chunks),
        )
        eng_resp = EngTaskResponse(
            task_id=task_id,
            answer=answer,
            retrieval=retrieval_res,
        )

        gate = QualityGate.default_gate()
        report = gate.check(request=eng_req, response=eng_resp, threshold=threshold)

        return {
            "task_id": task_id,
            "passed": report.passed,
            "aggregated_score": report.aggregated_score,
            "threshold_applied": report.threshold_applied,
            "critical_failures": report.critical_failures,
            "signals": [
                {
                    "signal_type": s.signal_type,
                    "status": s.status,
                    "score": s.score,
                    "weight": s.weight,
                    "rationale": s.rationale,
                    "metadata": s.metadata,
                }
                for s in report.signals
            ],
        }

    except Exception as exc:
        logger.error(f"Verification endpoint failed: {exc}")
        raise HTTPException(status_code=500, detail=str(exc))

