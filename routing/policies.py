"""
Engineering Intelligence Hub — Routing Policies
================================================
Configuration model for routing policy parameters.

Policies control how the router trades off quality, cost, latency and energy.
They are loaded from configs/default.yaml and can be overridden per experiment.

The optimisation objective (from the system specification) is:
    minimise: α*Time + β*Cost + γ*Energy + δ*CO2e + ε*Rework
    subject to: Quality ≥ task_specific_threshold

The weights α, β, γ, δ, ε are stored in RoutingPolicy and used by the
router to score candidate models.
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class RoutingPolicy(BaseModel):
    """
    Parameters controlling model selection trade-offs.

    All weight fields (alpha through epsilon) are dimensionless multipliers
    applied to normalised scores. Adjust to shift optimisation emphasis.
    """

    # --- Objective weights (must sum to meaningful ratio — not constrained to 1) ---
    alpha_latency: float = Field(
        default=0.25,
        description="Weight for normalised latency in the routing objective",
    )
    beta_cost: float = Field(
        default=0.25,
        description="Weight for normalised monetary cost",
    )
    gamma_energy: float = Field(
        default=0.25,
        description="Weight for normalised energy consumption",
    )
    delta_co2: float = Field(
        default=0.15,
        description="Weight for normalised CO2e emissions",
    )
    epsilon_rework: float = Field(
        default=0.10,
        description="Weight for estimated rework risk (proxy: escalation probability)",
    )

    # --- Escalation ---
    escalate_on_quality_fail: bool = Field(
        default=True,
        description="If True, escalate to next tier when quality gate fails",
    )
    max_escalation_steps: int = Field(
        default=2,
        description="Maximum number of tier escalations before returning best available",
        ge=0,
        le=5,
    )

    # --- Safety overrides ---
    force_large_for_critical: bool = Field(
        default=True,
        description="If True, always use LARGE or FRONTIER tier for CRITICAL tasks regardless of weights",
    )
    force_frontier_for_security: bool = Field(
        default=False,
        description="If True, use FRONTIER tier for HIGH security sensitivity tasks",
    )

    # --- Fallback ---
    fallback_model_id: Optional[str] = Field(
        default=None,
        description="Explicit fallback model if routing fails. None = use registry default.",
    )
