"""
Engineering Intelligence Hub — Monetary Cost Estimator
=======================================================
Estimates the monetary cost of LLM API calls based on token counts
and provider pricing tables.

IMPORTANT:
- Prices are volatile and change frequently. Always verify against
  official provider pricing pages before publishing results.
- These are ESTIMATES based on public list pricing.
- Discounts, enterprise pricing, and cached-token pricing are NOT modelled.
- Update costs in configs/models.yaml when prices change.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional


@dataclass
class CostEstimate:
    """Monetary cost estimate for a single generation call."""

    total_cost_usd: float
    input_cost_usd: float
    output_cost_usd: float
    input_tokens: int
    output_tokens: int
    model_id: str
    cost_per_1m_input_tokens: float
    cost_per_1m_output_tokens: float
    is_estimate: bool = True
    notes: str = ""


# ---------------------------------------------------------------------------
# Reference pricing table (USD per 1M tokens) — as of mid-2025.
# Source: Provider pricing pages. Update regularly.
# ---------------------------------------------------------------------------

_DEFAULT_PRICING: Dict[str, Dict[str, float]] = {
    # OpenAI
    "gpt-4o": {"input": 2.50, "output": 10.00},
    "gpt-4o-mini": {"input": 0.15, "output": 0.60},
    "gpt-3.5-turbo": {"input": 0.50, "output": 1.50},
    "o3-mini": {"input": 1.10, "output": 4.40},
    # Anthropic
    "claude-3-5-sonnet-20241022": {"input": 3.00, "output": 15.00},
    "claude-3-haiku-20240307": {"input": 0.25, "output": 1.25},
    "claude-3-opus-20240229": {"input": 15.00, "output": 75.00},
    # Google
    "gemini-1.5-pro": {"input": 3.50, "output": 10.50},
    "gemini-1.5-flash": {"input": 0.075, "output": 0.30},
    "gemini-2.0-flash": {"input": 0.10, "output": 0.40},
    # Together AI / open-weight models
    "meta-llama/Llama-3-70b-chat-hf": {"input": 0.90, "output": 0.90},
    "meta-llama/Llama-3-8b-chat-hf": {"input": 0.20, "output": 0.20},
    # Local models (no API cost)
    "local": {"input": 0.0, "output": 0.0},
}

_FALLBACK_PRICING = {"input": 1.00, "output": 4.00}  # Conservative unknown


class CostEstimator:
    """
    Estimates monetary cost for LLM generation calls.

    Parameters
    ----------
    pricing_table : dict, optional
        Custom pricing overrides. Format:
        {"model_id": {"input": float, "output": float}}
        Values are USD per 1M tokens.
    """

    def __init__(
        self,
        pricing_table: Optional[Dict[str, Dict[str, float]]] = None,
    ) -> None:
        self._pricing: Dict[str, Dict[str, float]] = dict(_DEFAULT_PRICING)
        if pricing_table:
            self._pricing.update(pricing_table)

    def estimate(
        self,
        input_tokens: int,
        output_tokens: int,
        model_id: str,
    ) -> CostEstimate:
        """
        Estimate the cost of a generation call.

        Parameters
        ----------
        input_tokens : int
        output_tokens : int
        model_id : str
            Must match a key in the pricing table. If unknown, the
            fallback pricing is used and flagged in notes.
        """
        pricing = self._pricing.get(model_id)
        used_fallback = pricing is None

        if pricing is None:
            # Try prefix matching (e.g. "gpt-4o-mini-2024-07-18" → "gpt-4o-mini")
            for key in self._pricing:
                if model_id.startswith(key):
                    pricing = self._pricing[key]
                    used_fallback = False
                    break

        if pricing is None:
            pricing = _FALLBACK_PRICING
            used_fallback = True

        input_cost = (input_tokens / 1_000_000) * pricing["input"]
        output_cost = (output_tokens / 1_000_000) * pricing["output"]
        total_cost = input_cost + output_cost

        return CostEstimate(
            total_cost_usd=round(total_cost, 8),
            input_cost_usd=round(input_cost, 8),
            output_cost_usd=round(output_cost, 8),
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            model_id=model_id,
            cost_per_1m_input_tokens=pricing["input"],
            cost_per_1m_output_tokens=pricing["output"],
            is_estimate=True,
            notes=(
                f"{'FALLBACK pricing used — verify against provider pricing page' if used_fallback else 'Pricing from table'}. "
                "Excludes discounts, caching, and enterprise pricing."
            ),
        )

    def register_model_pricing(
        self, model_id: str, input_cost_per_1m: float, output_cost_per_1m: float
    ) -> None:
        """Add or update pricing for a model."""
        self._pricing[model_id] = {"input": input_cost_per_1m, "output": output_cost_per_1m}
