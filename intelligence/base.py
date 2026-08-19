"""
Engineering Intelligence Hub — Task Intelligence Base Interface
================================================================
Defines the abstract interface for task analysis and classification.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from knowledge.schemas.tasks import EngTaskRequest, TaskClassification


class BaseTaskClassifier(ABC):
    """
    Abstract base class for engineering task classification.

    Analyzes an incoming EngTaskRequest and produces a structured TaskClassification
    containing SDLC stage, task type, complexity, criticality, security sensitivity,
    and quality requirements.
    """

    @property
    @abstractmethod
    def classifier_name(self) -> str:
        """Human-readable identifier for this classifier implementation."""
        pass

    @abstractmethod
    def classify(self, request: EngTaskRequest) -> TaskClassification:
        """
        Classify an engineering task request.

        Parameters
        ----------
        request : EngTaskRequest
            The incoming user engineering query and metadata.

        Returns
        -------
        TaskClassification
            Structured classification driving downstream retrieval, routing, and verification.
        """
        pass
