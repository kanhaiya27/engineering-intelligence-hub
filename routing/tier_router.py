"""
Engineering Intelligence Hub — tier-based model router for the local ladder
===========================================================================
Selects small / medium / large (Qwen2.5-Coder 1.5B / 3B / 7B) from the task's
classification, and escalates one tier when the quality gate fails.

BASELINE HEURISTIC, like the retrieval policies: the rules below are an initial,
interpretable configuration to be evaluated (RQ4), not a claim of optimality.

  large  : criticality HIGH or CRITICAL (if policy.force_large_for_critical),
           security sensitivity HIGH, or complexity HIGH / VERY_HIGH
  small  : complexity LOW with criticality LOW or MEDIUM
  medium : everything else (including UNKNOWN)
"""

from __future__ import annotations

from typing import List, Optional

from core.logging import get_logger
from knowledge.schemas.tasks import TaskClassification
from routing.base import BaseModelRouter
from routing.policies import RoutingPolicy
from routing.registry import ModelProvider, ModelRegistry, ModelTier

logger = get_logger(__name__)

TIER_ORDER = [ModelTier.SMALL.value, ModelTier.MEDIUM.value, ModelTier.LARGE.value]


def _value(x) -> str:
    return getattr(x, "value", x) or "unknown"


class RoutingError(RuntimeError):
    pass


class TierRouter(BaseModelRouter):
    """Complexity/criticality tier router with one-step escalation."""

    def __init__(self, registry: ModelRegistry, policy: Optional[RoutingPolicy] = None,
                 local_only: bool = True) -> None:
        super().__init__(registry)
        self.policy = policy or RoutingPolicy()
        self.local_only = local_only
        self._ladder = self._build_ladder()

    @property
    def router_name(self) -> str:
        return "tier_router_v1"

    def _build_ladder(self) -> List[str]:
        ladder = []
        for tier in TIER_ORDER:
            candidates = [p for p in self.registry.list_by_tier(ModelTier(tier))
                          if not self.local_only or p.provider == ModelProvider.LOCAL.value]
            if not candidates:
                raise RoutingError(f"No {'local ' if self.local_only else ''}model registered for tier '{tier}'")
            ladder.append(candidates[0].model_id)
        return ladder

    @property
    def ladder(self) -> List[str]:
        """Model ids from smallest to largest."""
        return list(self._ladder)

    def tier_for(self, classification: TaskClassification) -> str:
        complexity = _value(classification.complexity)
        criticality = _value(classification.criticality)
        security = _value(getattr(classification, "security_sensitivity", None))
        if self.policy.force_large_for_critical and criticality in ("high", "critical"):
            return ModelTier.LARGE.value
        if security == "high" or complexity in ("high", "very_high"):
            return ModelTier.LARGE.value
        if complexity == "low" and criticality in ("low", "medium"):
            return ModelTier.SMALL.value
        return ModelTier.MEDIUM.value

    def select_model(self, classification: TaskClassification,
                     override_model_id: Optional[str] = None) -> str:
        if override_model_id:
            return override_model_id
        model_id = self._ladder[TIER_ORDER.index(self.tier_for(classification))]
        logger.info(f"Router selected {model_id} for task {classification.task_id} "
                    f"(complexity={_value(classification.complexity)}, "
                    f"criticality={_value(classification.criticality)})")
        return model_id

    def escalate(self, model_id: str) -> str:
        """Next larger model on the ladder; the largest stays the largest."""
        if not self.policy.escalate_on_quality_fail or model_id not in self._ladder:
            return model_id
        i = self._ladder.index(model_id)
        return self._ladder[min(i + 1, len(self._ladder) - 1)]
