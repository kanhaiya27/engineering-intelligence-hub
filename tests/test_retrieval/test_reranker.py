"""
Tests for the cross-encoder reranking stage.

REGRESSION INTENT
-----------------
The defect these tests exist to prevent: `enable_reranking=True` silently
producing unreranked output. Before `retrieval/reranker.py` existed, nothing read
`enable_reranking` / `reranker_type` / `reranker_top_n`, so `hybrid_reranked` and
`graph_augmented_reranked` — the strategies used for HIGH/CRITICAL tasks and for
the final escalation rung — quietly behaved as plain hybrid fusion.

Most tests here use a deterministic fake reranker so the suite stays hermetic and
fast. The single test that loads the real cross-encoder is marked `integration`
and skips when the model is unavailable offline.
"""

from __future__ import annotations

import pytest

from core.exceptions import RetrievalError
from knowledge.schemas.tasks import RetrievedChunk
from retrieval.reranker import (
    BaseReranker,
    CrossEncoderReranker,
    RerankOutcome,
    apply_reranking,
    get_reranker,
    reset_reranker_cache,
)
from retrieval.strategies import RerankerType, RetrievalStrategyConfig


def _chunks() -> list[RetrievedChunk]:
    """Three chunks whose fused order is deliberately WRONG for the query."""
    return [
        RetrievedChunk(chunk_id="irrelevant", content="pip install flask", score=0.95),
        RetrievedChunk(chunk_id="wrong_key", content="SECRET_KEY signs session cookies", score=0.60),
        RetrievedChunk(chunk_id="correct", content="The DEBUG key enables the debugger", score=0.20),
    ]


class ReversingReranker(BaseReranker):
    """Deterministic stand-in: reverses candidate order, no model required."""

    @property
    def reranker_name(self) -> str:
        return "reversing_fake"

    def rerank(self, query, chunks, top_n):
        reversed_chunks = list(chunks)[::-1][:top_n]
        return RerankOutcome(
            chunks=reversed_chunks,
            applied=True,
            reranker_type=RerankerType.CROSS_ENCODER.value,
            model_id="fake",
            device="cpu",
            latency_ms=1.0,
            candidates_in=len(chunks),
            returned=len(reversed_chunks),
            energy_joules=0.001,
            energy_method="tdp_proxy",
        )


class ExplodingReranker(BaseReranker):
    """Simulates a model that fails to load or infer."""

    @property
    def reranker_name(self) -> str:
        return "exploding_fake"

    def rerank(self, query, chunks, top_n):
        raise RuntimeError("CUDA out of memory")


class TestRerankingIsActuallyApplied:
    """The core regression: enabling reranking must change the output."""

    def test_reranking_reorders_and_truncates_to_top_n(self):
        strategy = RetrievalStrategyConfig(
            strategy_name="hybrid_reranked",
            enable_reranking=True,
            reranker_type=RerankerType.CROSS_ENCODER,
            reranker_top_n=2,
            max_context_chunks=5,
        )
        outcome = apply_reranking(
            query="which key controls debug mode?",
            chunks=_chunks(),
            strategy=strategy,
            reranker=ReversingReranker(),
        )

        assert outcome.applied is True
        assert outcome.returned == 2
        # Reversal puts the correct chunk first — proving order actually changed.
        assert outcome.chunks[0].chunk_id == "correct"

    def test_disabled_reranking_is_a_documented_passthrough(self):
        strategy = RetrievalStrategyConfig(
            strategy_name="hybrid",
            enable_reranking=False,
        )
        chunks = _chunks()
        outcome = apply_reranking(query="q", chunks=chunks, strategy=strategy)

        assert outcome.applied is False
        assert outcome.error is None
        assert [c.chunk_id for c in outcome.chunks] == [c.chunk_id for c in chunks]

    def test_outcome_metadata_states_whether_reranking_ran(self):
        """Every experiment trace must be able to prove reranking happened."""
        strategy = RetrievalStrategyConfig(
            strategy_name="hybrid_reranked",
            enable_reranking=True,
            reranker_type=RerankerType.CROSS_ENCODER,
            reranker_top_n=2,
        )
        meta = apply_reranking(
            query="q", chunks=_chunks(), strategy=strategy, reranker=ReversingReranker()
        ).as_metadata()

        assert meta["reranking_applied"] is True
        assert meta["reranker_candidates_in"] == 3
        assert meta["reranker_returned"] == 2
        assert "reranker_energy_joules" in meta


class TestFailLoudNeverSilently:
    """A broken reranker must be visible, never a silent pass-through."""

    def test_failure_records_error_and_preserves_candidates(self):
        strategy = RetrievalStrategyConfig(
            strategy_name="hybrid_reranked",
            enable_reranking=True,
            reranker_type=RerankerType.CROSS_ENCODER,
            reranker_top_n=2,
        )
        outcome = apply_reranking(
            query="q", chunks=_chunks(), strategy=strategy, reranker=ExplodingReranker()
        )

        assert outcome.applied is False
        assert "CUDA out of memory" in outcome.error
        assert outcome.returned == 3  # original candidates preserved
        assert outcome.as_metadata()["reranker_error"]

    def test_unsupported_reranker_type_is_flagged_not_ignored(self):
        """cohere_rerank is declared in the enum but intentionally unimplemented."""
        strategy = RetrievalStrategyConfig(
            strategy_name="cohere_strategy",
            enable_reranking=True,
            reranker_type=RerankerType.COHERE_RERANK,
            reranker_top_n=2,
        )
        outcome = apply_reranking(query="q", chunks=_chunks(), strategy=strategy)

        assert outcome.applied is False
        assert "unsupported_reranker_type" in outcome.error

    def test_strict_mode_raises_instead_of_degrading(self, monkeypatch):
        """Final experiment runs must not tolerate a silently skipped reranker."""
        from core.config import settings

        monkeypatch.setattr(settings.retrieval, "strict_reranking", True, raising=False)
        strategy = RetrievalStrategyConfig(
            strategy_name="hybrid_reranked",
            enable_reranking=True,
            reranker_type=RerankerType.CROSS_ENCODER,
            reranker_top_n=2,
        )
        with pytest.raises(RetrievalError):
            apply_reranking(
                query="q", chunks=_chunks(), strategy=strategy, reranker=ExplodingReranker()
            )


class TestRerankerFactory:
    def test_none_type_returns_no_reranker(self):
        assert get_reranker(RerankerType.NONE.value) is None

    def test_cohere_is_unimplemented_by_design(self):
        assert get_reranker(RerankerType.COHERE_RERANK.value) is None

    def test_cross_encoder_resolves_and_is_cached(self):
        reset_reranker_cache()
        first = get_reranker(RerankerType.CROSS_ENCODER.value)
        second = get_reranker(RerankerType.CROSS_ENCODER.value)
        assert isinstance(first, CrossEncoderReranker)
        assert first is second  # cached — model load must not repeat per query
        reset_reranker_cache()


class TestConfiguredStrategiesRequestReranking:
    """Guards the YAML contract these strategies advertise."""

    @pytest.mark.parametrize(
        "strategy_name", ["hybrid_reranked", "graph_augmented_reranked"]
    )
    def test_declared_reranked_strategies_have_a_real_implementation(self, strategy_name):
        from retrieval.router import RetrievalRouter

        router = RetrievalRouter.from_yaml("configs/retrieval.yaml")
        strategy = router.list_strategies()[strategy_name]

        assert strategy.enable_reranking is True
        # The declared reranker type must actually resolve to an implementation,
        # otherwise the strategy is advertising a capability it does not have.
        assert get_reranker(strategy.reranker_type) is not None


@pytest.mark.integration
class TestRealCrossEncoder:
    """Loads the actual model — skipped when unavailable (e.g. offline CI)."""

    def test_real_model_promotes_the_relevant_chunk(self):
        try:
            reranker = CrossEncoderReranker()
            outcome = reranker.rerank(
                query="Which configuration key controls debug mode in Flask?",
                chunks=_chunks(),
                top_n=1,
            )
        except Exception as exc:  # noqa: BLE001 - model download unavailable
            pytest.skip(f"Cross-encoder model unavailable: {exc}")

        assert outcome.applied is True
        # Fusion ranked "pip install flask" first; the cross-encoder must fix that.
        assert outcome.chunks[0].chunk_id == "correct"
        assert outcome.chunks[0].metadata["pre_rerank_rank"] == 2
        assert outcome.chunks[0].metadata["post_rerank_rank"] == 0

    def test_cold_start_is_excluded_from_per_query_energy(self):
        """Model load must never be billed as reranking cost."""
        try:
            reranker = CrossEncoderReranker()
            reranker.rerank(query="warm up", chunks=_chunks(), top_n=1)
            warm = reranker.rerank(query="second call", chunks=_chunks(), top_n=1)
        except Exception as exc:  # noqa: BLE001
            pytest.skip(f"Cross-encoder model unavailable: {exc}")

        assert warm.cold_start_ms == 0.0
        # A warm forward pass over 3 short chunks is milliseconds, not seconds.
        assert warm.latency_ms < 1000.0
