"""
Engineering Intelligence Hub — Bounded Escalation Policy (M4)
=============================================================
Deterministic, bounded progression for escalating retrieval strategies
when a generated response fails verification against task quality thresholds.

Progression Ladder:
  Attempt 0: Initial adaptive strategy (resolved from task classification)
  Attempt 1: Expanded retrieval (increase top_k, max_context_chunks, lower score_threshold)
  Attempt 2: Graph augmentation (activate graph neighbourhood traversal, hop_depth=2)
  Attempt 3: Maximal capability (graph_augmented_reranked or hybrid_reranked)

All escalation is strictly bounded by `max_attempts`.
When attempts are exhausted, the pipeline returns INSUFFICIENT_EVIDENCE
rather than hallucinating low-quality content.
"""

from __future__ import annotations

from typing import Optional

from core.logging import get_logger
from retrieval.strategies import RerankerType, RetrievalMode, RetrievalStrategyConfig
from verification.config import VerificationConfig
from verification.signals import QualityReport

logger = get_logger(__name__)


class EscalationPolicy:
    """
    Determines how to strengthen retrieval when verification fails.
    """

    def __init__(self, config: Optional[VerificationConfig] = None) -> None:
        self._config = config or VerificationConfig()

    def get_max_attempts(self) -> int:
        """Return the maximum allowed escalation attempts."""
        return self._config.max_escalation_attempts

    def escalate(
        self,
        current_strategy: RetrievalStrategyConfig,
        attempt: int,
        report: Optional[QualityReport] = None,
    ) -> RetrievalStrategyConfig:
        """
        Produce a stronger RetrievalStrategyConfig for the next attempt.

        Parameters
        ----------
        current_strategy : RetrievalStrategyConfig
            The strategy used in the failed attempt.
        attempt : int
            The upcoming escalation attempt index (1, 2, 3...).
        report : QualityReport, optional
            The failed quality report (for error-directed escalation).

        Returns
        -------
        RetrievalStrategyConfig
            Escalated strategy with richer retrieval parameters.
        """
        top_k_delta = self._config.escalation_top_k_delta
        graph_depth = self._config.escalation_graph_depth

        logger.info(
            f"Escalating retrieval strategy '{current_strategy.strategy_name}' "
            f"on attempt {attempt} (score={report.aggregated_score if report else 'N/A'})"
        )

        if attempt == 1:
            # Step 1: Broaden search scope — increase top_k and lower threshold
            new_top_k = min(20, current_strategy.top_k + top_k_delta)
            new_max_ctx = min(15, current_strategy.max_context_chunks + top_k_delta)
            new_threshold = max(0.0, current_strategy.score_threshold - 0.05)

            return current_strategy.model_copy(
                update={
                    "strategy_name": f"{current_strategy.strategy_name}_esc1",
                    "top_k": new_top_k,
                    "max_context_chunks": new_max_ctx,
                    "score_threshold": round(new_threshold, 2),
                }
            )

        elif attempt == 2:
            # Step 2: Activate graph neighborhood context injection
            new_top_k = min(25, current_strategy.top_k + (top_k_delta * 2))
            new_max_ctx = min(18, current_strategy.max_context_chunks + (top_k_delta * 2))

            return current_strategy.model_copy(
                update={
                    "strategy_name": f"{current_strategy.strategy_name}_esc2_graph",
                    "mode": RetrievalMode.GRAPH_AUGMENTED,
                    "include_graph_context": True,
                    "graph_hop_depth": graph_depth,
                    "top_k": new_top_k,
                    "max_context_chunks": new_max_ctx,
                    "score_threshold": max(0.0, current_strategy.score_threshold - 0.10),
                }
            )

        else:
            # Step 3+: Maximal capability — graph augmented with cross-encoder reranking.
            #
            # reranker_type MUST be set here alongside enable_reranking. Setting
            # only the flag inherits reranker_type="none" from the base strategy,
            # which resolves to no implementation — the rung would report itself
            # as reranked while performing no reranking at all. Widening top_k to
            # 30 is only useful BECAUSE the cross-encoder then re-scores that
            # wider pool down to reranker_top_n; without it, 30 loosely-fused
            # chunks is worse context, not better.
            return current_strategy.model_copy(
                update={
                    "strategy_name": f"{current_strategy.strategy_name}_esc_max",
                    "mode": RetrievalMode.GRAPH_AUGMENTED,
                    "include_graph_context": True,
                    "graph_hop_depth": min(3, graph_depth + 1),
                    "enable_reranking": True,
                    "reranker_type": RerankerType.CROSS_ENCODER,
                    "reranker_top_n": 10,
                    "top_k": 30,
                    "max_context_chunks": 20,
                    "score_threshold": 0.0,
                }
            )
