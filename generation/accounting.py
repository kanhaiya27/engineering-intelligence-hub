"""
Engineering Intelligence Hub — per-generation energy, carbon and cost accounting
================================================================================
One rule for every pipeline: when the provider MEASURED the GPU energy of the
call (OllamaProvider, NVML energy counter), that measurement is used; only when
it did not (API providers, mocks) does the TDP-proxy estimator run, and the
result is then labelled ESTIMATED. Every figure carries its measurement tier.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional

from generation.base import GenerationResponse


@dataclass
class GenerationAccount:
    energy_joules: float
    energy_tier: str            # MEASURED | ESTIMATED
    co2e_grams: float
    co2e_tier: str              # ESTIMATED: energy x an average grid intensity (original plan §9.1)
    cost_usd: float
    cost_tier: str              # ESTIMATED (original plan §9.1); 0 for local inference
    energy_reliability: Optional[str] = None
    cold_start: Optional[Dict[str, Any]] = None

    def as_metadata(self) -> Dict[str, Any]:
        return {
            "energy_joules": self.energy_joules, "energy_tier": self.energy_tier,
            "co2e_grams": self.co2e_grams, "co2e_tier": self.co2e_tier,
            "cost_usd": self.cost_usd, "cost_tier": self.cost_tier,
            "energy_reliability": self.energy_reliability,
            "cold_start": self.cold_start,
        }


def account_generation(
    gen: GenerationResponse,
    model_id: str,
    energy_estimator,
    carbon_estimator,
    cost_estimator,
) -> GenerationAccount:
    extra = gen.extra or {}
    tiers = extra.get("measurement_tiers") or {}
    if tiers.get("energy_joules") == "MEASURED" and extra.get("energy_joules") is not None:
        energy_j = float(extra["energy_joules"])
        co2e_g = (energy_j / 3_600_000.0) * carbon_estimator.carbon_intensity
        return GenerationAccount(
            energy_joules=energy_j, energy_tier="MEASURED",
            co2e_grams=co2e_g, co2e_tier="ESTIMATED",
            cost_usd=float(extra.get("cost_usd", 0.0) or 0.0), cost_tier="ESTIMATED",
            energy_reliability=extra.get("energy_reliability"),
            cold_start=extra.get("cold_start"),
        )

    energy_est = energy_estimator.estimate(
        latency_ms=gen.latency_ms,
        input_tokens=gen.input_tokens or 0,
        output_tokens=gen.output_tokens or 0,
        model_id=model_id,
        is_local_model=False,
    )
    carbon_est = carbon_estimator.estimate(energy_estimate=energy_est)
    cost_est = cost_estimator.estimate(
        input_tokens=gen.input_tokens or 0,
        output_tokens=gen.output_tokens or 0,
        model_id=model_id,
    )
    return GenerationAccount(
        energy_joules=energy_est.energy_joules, energy_tier="ESTIMATED",
        co2e_grams=carbon_est.co2e_grams, co2e_tier="ESTIMATED",
        cost_usd=cost_est.total_cost_usd, cost_tier="ESTIMATED",
    )
