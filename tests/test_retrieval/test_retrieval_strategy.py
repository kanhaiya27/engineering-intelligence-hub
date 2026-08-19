"""Tests for retrieval strategy configuration."""

from __future__ import annotations

import pytest

from retrieval.strategies import RetrievalMode, RetrievalStrategyConfig


class TestRetrievalStrategyConfig:
    def test_default_strategy(self):
        s = RetrievalStrategyConfig(strategy_name="test")
        assert s.mode == RetrievalMode.HYBRID
        assert s.top_k == 5
        assert s.enable_reranking is False

    def test_dense_strategy(self):
        s = RetrievalStrategyConfig(
            strategy_name="dense",
            mode=RetrievalMode.DENSE,
            top_k=3,
            score_threshold=0.70,
        )
        assert s.mode == RetrievalMode.DENSE
        assert s.top_k == 3

    def test_top_k_bounds(self):
        with pytest.raises(Exception):
            RetrievalStrategyConfig(strategy_name="bad", top_k=0)
        with pytest.raises(Exception):
            RetrievalStrategyConfig(strategy_name="bad", top_k=51)

    def test_score_threshold_bounds(self):
        with pytest.raises(Exception):
            RetrievalStrategyConfig(strategy_name="bad", score_threshold=1.5)
        with pytest.raises(Exception):
            RetrievalStrategyConfig(strategy_name="bad", score_threshold=-0.1)

    def test_graph_augmented_strategy(self):
        s = RetrievalStrategyConfig(
            strategy_name="graph_aug",
            mode=RetrievalMode.GRAPH_AUGMENTED,
            include_graph_context=True,
            graph_hop_depth=2,
        )
        assert s.include_graph_context is True
        assert s.graph_hop_depth == 2

    def test_serialisation_roundtrip(self):
        s = RetrievalStrategyConfig(
            strategy_name="hybrid_reranked",
            mode=RetrievalMode.HYBRID,
            top_k=10,
            enable_reranking=True,
            reranker_top_n=5,
        )
        data = s.model_dump()
        restored = RetrievalStrategyConfig(**data)
        assert restored.strategy_name == "hybrid_reranked"
        assert restored.enable_reranking is True
        assert restored.reranker_top_n == 5
