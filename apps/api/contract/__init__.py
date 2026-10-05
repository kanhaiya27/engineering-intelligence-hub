"""
Versioned API contracts for the EIH web platform.

``apps.api.contract.v1`` is the frozen interface between the research pipeline
(Laptop A) and the web platform (Laptop B). See ``docs/API_CONTRACT.md``.
"""

from apps.api.contract.v1 import CONTRACT_VERSION

__all__ = ["CONTRACT_VERSION"]
