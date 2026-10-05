"""
Tests for the adaptive retrieval REST endpoint (/adaptive/retrieve).
"""

from unittest.mock import MagicMock

from fastapi.testclient import TestClient

from apps.api.main import app
from apps.api.routers import adaptive as adaptive_router
from retrieval.adaptive import AdaptiveRetrievalPipeline
from retrieval.policy import AdaptiveRetrievalPolicy
from retrieval.strategies import RetrievalStrategyConfig

client = TestClient(app)


def _offline_pipeline() -> AdaptiveRetrievalPipeline:
    registry = {"hybrid": RetrievalStrategyConfig(strategy_name="hybrid")}
    pipeline = AdaptiveRetrievalPipeline.__new__(AdaptiveRetrievalPipeline)
    pipeline._registry = registry
    pipeline._policy = AdaptiveRetrievalPolicy(registry)
    pipeline._graph_store = None
    for attr in ("_dense", "_sparse", "_hybrid", "_graph_aug", "_router"):
        setattr(pipeline, attr, MagicMock())
    return pipeline


def test_unknown_override_strategy_returns_400(monkeypatch):
    # An unknown strategy name used to run "hybrid" silently (finding F1).
    pipeline = _offline_pipeline()
    monkeypatch.setattr(adaptive_router, "_pipeline", pipeline)

    res = client.post(
        "/adaptive/retrieve",
        json={"query": "How does routing work?", "override_strategy": "hybrid_esc1"},
    )

    assert res.status_code == 400
    assert "hybrid_esc1" in res.json()["detail"]
    pipeline._hybrid.retrieve.assert_not_called()
