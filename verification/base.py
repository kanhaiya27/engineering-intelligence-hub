"""
Engineering Intelligence Hub — Abstract Quality Evaluator Interface
===================================================================
All quality evaluators must implement BaseQualityEvaluator.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import List

from knowledge.schemas.tasks import EngTaskRequest, EngTaskResponse
from verification.signals import QualitySignal


class BaseQualityEvaluator(ABC):
    """
    Abstract interface for a single quality evaluation dimension.

    Examples of concrete implementations (Phase-1):
      - GroundednessEvaluator  : checks answer is supported by retrieved context
      - RelevanceEvaluator     : checks answer addresses the query
      - CorrectnessEvaluator   : checks against ground truth (benchmark mode)
      - CodeCompilationChecker : attempts to compile/parse generated code
      - TestExecutionChecker   : runs generated tests against a codebase
    """

    @property
    @abstractmethod
    def evaluator_name(self) -> str:
        """Human-readable evaluator name."""
        ...

    @property
    @abstractmethod
    def signal_type(self) -> str:
        """The SignalType this evaluator produces."""
        ...

    @abstractmethod
    def evaluate(
        self,
        request: EngTaskRequest,
        response: EngTaskResponse,
    ) -> List[QualitySignal]:
        """
        Evaluate the response to a request and return quality signals.

        Parameters
        ----------
        request : EngTaskRequest
            The original task request.
        response : EngTaskResponse
            The generated response to evaluate.

        Returns
        -------
        List[QualitySignal]
            One or more signals. Most evaluators return exactly one signal.

        Notes
        -----
        - Must NOT raise — catch all internal errors and return a signal
          with status=ERROR instead.
        - Must NOT modify request or response.
        """
        ...

    def is_applicable(self, request: EngTaskRequest) -> bool:
        """
        Return True if this evaluator is applicable to the given task type.
        Default: True (applies to all tasks).
        Override to restrict to specific task types.
        """
        return True
