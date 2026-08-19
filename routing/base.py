"""
Engineering Intelligence Hub — Abstract Model Router Interface
=============================================================
Defines the contract for model routing strategies.

The router receives a TaskClassification and returns the model_id
to use for generation. It should select the cheapest/fastest model
that is expected to meet the quality threshold.

Phase-0: Interface only.
Phase-1: Implement TierBasedRouter (rule-based) and ThresholdRouter
         (quality-threshold-aware cost-minimising selection).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional

from knowledge.schemas.tasks import TaskClassification
from routing.registry import ModelCapabilityProfile, ModelRegistry


class BaseModelRouter(ABC):
    """
    Abstract interface for model selection/routing.

    A router maps a TaskClassification to a model_id string.
    The selected model is then used by the generation layer.
    """

    def __init__(self, registry: ModelRegistry) -> None:
        self.registry = registry

    @property
    @abstractmethod
    def router_name(self) -> str:
        """Human-readable router name for experiment logging."""
        ...

    @abstractmethod
    def select_model(
        self,
        classification: TaskClassification,
        override_model_id: Optional[str] = None,
    ) -> str:
        """
        Select the model_id for a given task.

        Parameters
        ----------
        classification : TaskClassification
            Fully populated task classification.
        override_model_id : str, optional
            Force a specific model (used in ablation/baseline experiments).

        Returns
        -------
        str
            A model_id that is registered in the ModelRegistry.

        Raises
        ------
        RoutingError
            If no suitable model can be found.
        """
        ...

    def get_profile(self, model_id: str) -> Optional[ModelCapabilityProfile]:
        """Convenience: look up a model profile from the registry."""
        return self.registry.get(model_id)
