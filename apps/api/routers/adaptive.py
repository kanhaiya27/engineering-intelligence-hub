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
        from retrieval.policy import _TASK_TYPE_STRATEGY_MAP, _CRITICALITY_OVERRIDE_MAP
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
            "experiment_modes": ["baseline_b", "system_c", "system_d"],
            "note": (
                "All policy mappings are initial heuristic configurations. "
                "They will be validated and tuned in Phase-2 M5 controlled evaluation."
            ),
        }
    except Exception as exc:
        logger.error(f"Failed to list strategies: {exc}")
        raise HTTPException(status_code=500, detail=str(exc))
