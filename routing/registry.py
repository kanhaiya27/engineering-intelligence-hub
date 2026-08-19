"""
Engineering Intelligence Hub — Model Capability Registry
=========================================================
Defines ModelCapabilityProfile — the metadata record for each model
registered in the system.

These profiles drive routing decisions: given task complexity, criticality
and quality requirements, the router selects the cheapest model that is
expected to meet the quality threshold.

Profiles are loaded from configs/models.yaml.

IMPORTANT: Cost, energy and latency figures in this file are approximate
reference values from public pricing/benchmarks. Actual measured values
will be collected during experiments and may differ significantly.
All figures must be verified and updated as experiments are conducted.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class ModelTier(str, Enum):
    """
    Capability tier used for routing.
    A SMALL model is tried first; LARGE / FRONTIER are reserved for
    high-complexity / high-criticality tasks or escalation.
    """
    SMALL = "small"       # e.g. gpt-4o-mini, Llama-3-8B
    MEDIUM = "medium"     # e.g. gpt-4o, Claude-3-Haiku
    LARGE = "large"       # e.g. Claude-3.5-Sonnet, Gemini-1.5-Pro
    FRONTIER = "frontier" # e.g. o3, Claude-3.5-Opus
    LOCAL = "local"       # Self-hosted (Ollama, vLLM)


class ModelProvider(str, Enum):
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    GOOGLE = "google"
    TOGETHER = "together"
    HUGGINGFACE = "huggingface"
    LOCAL = "local"
    OTHER = "other"


class ModelCapabilityProfile(BaseModel):
    """
    Reference capability and cost profile for one model.

    All cost/energy/latency fields are REFERENCE ESTIMATES for planning.
    Actual values are measured during experiments and stored in experiment logs.
    """

    model_id: str = Field(description="Unique model identifier used in API calls")
    display_name: str = Field(description="Human-readable name")
    provider: ModelProvider
    tier: ModelTier

    # --- Context ---
    context_window_tokens: int = Field(
        description="Maximum total tokens (prompt + completion)"
    )
    max_output_tokens: int = Field(description="Maximum completion tokens")

    # --- Reference cost (USD per 1M tokens) ---
    # Source these from provider pricing pages. Mark as None if unknown.
    ref_input_cost_per_1m_tokens: Optional[float] = Field(
        default=None,
        description="Reference input token cost in USD/1M — verify against provider pricing",
    )
    ref_output_cost_per_1m_tokens: Optional[float] = Field(
        default=None,
        description="Reference output token cost in USD/1M — verify against provider pricing",
    )

    # --- Reference latency ---
    ref_latency_p50_ms: Optional[float] = Field(
        default=None,
        description="Median latency in milliseconds — from public benchmarks or own measurement",
    )
    ref_latency_p95_ms: Optional[float] = Field(
        default=None,
        description="P95 latency in milliseconds",
    )

    # --- Energy proxy ---
    # True measurement requires controlled experiments.
    # These are placeholder proxies based on model size / provider guidance.
    ref_energy_per_1k_output_tokens_wh: Optional[float] = Field(
        default=None,
        description=(
            "Reference energy in Wh per 1000 output tokens. "
            "PLACEHOLDER — replace with measured values from experiments."
        ),
    )

    # --- Capabilities ---
    supports_function_calling: bool = Field(default=False)
    supports_code_execution: bool = Field(default=False)
    supports_vision: bool = Field(default=False)
    supports_streaming: bool = Field(default=True)
    is_available_locally: bool = Field(
        default=False,
        description="True if model can be run on local hardware",
    )

    # --- Routing hints ---
    recommended_for_task_types: List[str] = Field(
        default_factory=list,
        description="Task types this model is particularly well-suited for",
    )
    not_recommended_for: List[str] = Field(
        default_factory=list,
        description="Task types this model should not be used for",
    )

    # --- Configuration ---
    default_temperature: float = Field(default=0.1)
    default_max_tokens: int = Field(default=2048)
    api_base_url: Optional[str] = Field(
        default=None,
        description="Override API base URL (for local/self-hosted models)",
    )
    extra: Dict[str, Any] = Field(default_factory=dict)

    class Config:
        use_enum_values = True


class ModelRegistry:
    """
    In-memory registry of ModelCapabilityProfile instances.
    Loaded from configs/models.yaml at startup.
    """

    def __init__(self) -> None:
        self._profiles: Dict[str, ModelCapabilityProfile] = {}

    def register(self, profile: ModelCapabilityProfile) -> None:
        """Add or replace a model profile."""
        self._profiles[profile.model_id] = profile

    def get(self, model_id: str) -> Optional[ModelCapabilityProfile]:
        """Return the profile for model_id, or None if not registered."""
        return self._profiles.get(model_id)

    def list_by_tier(self, tier: ModelTier) -> List[ModelCapabilityProfile]:
        """Return all profiles for a given tier, sorted by reference cost (ascending)."""
        profiles = [p for p in self._profiles.values() if p.tier == tier]
        return sorted(
            profiles,
            key=lambda p: p.ref_input_cost_per_1m_tokens or float("inf"),
        )

    def list_all(self) -> List[ModelCapabilityProfile]:
        return list(self._profiles.values())

    @classmethod
    def from_yaml(cls, yaml_path: str) -> "ModelRegistry":
        """Load registry from configs/models.yaml."""
        import yaml as _yaml

        with open(yaml_path, "r", encoding="utf-8") as f:
            raw = _yaml.safe_load(f) or {}

        registry = cls()
        for model_data in raw.get("models", []):
            profile = ModelCapabilityProfile(**model_data)
            registry.register(profile)

        return registry

    def __len__(self) -> int:
        return len(self._profiles)

    def __repr__(self) -> str:  # pragma: no cover
        return f"ModelRegistry({len(self._profiles)} models)"
