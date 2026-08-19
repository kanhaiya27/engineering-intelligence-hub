"""
Engineering Intelligence Hub — Sustainability Measurement Base
==============================================================
Abstract interface for resource and sustainability measurement.

SYSTEM BOUNDARY DECLARATION
----------------------------
The sustainability estimates produced by this system cover:

Included (Scope):
  - Token processing time (wall-clock latency as proxy for compute energy)
  - CPU utilisation during processing (via psutil)
  - GPU utilisation during processing (via pynvml if available)
  - Estimated energy from TDP proxies when direct measurement unavailable
  - Monetary cost based on token counts and provider pricing

Excluded (Out of Scope):
  - Network transmission energy (client ↔ provider API calls)
  - Data centre embodied carbon (manufacturing of hardware)
  - Cooling overhead (PUE factor not applied by default — configurable)
  - Training energy of the underlying LLMs

IMPORTANT:
  - These estimates are for comparative/research purposes.
  - Do not use them as precise environmental impact claims without
    disclosure of the above exclusions and methodology.
  - Always report estimates with their uncertainty and assumptions.
  - Carbon intensity varies by region and time. Default uses UK 2024 average.

References:
  - UK grid carbon intensity: National Grid ESO (2024), ~233 gCO2e/kWh
  - AI energy estimation methodology: Patterson et al. (2021),
    "Carbon and the Carbon Footprint of Machine Learning"
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from sustainability.energy.estimator import EnergyEstimate
from sustainability.cost.estimator import CostEstimate
from sustainability.carbon.estimator import CarbonEstimate


class BaseResourceMeasurement(ABC):
    """
    Abstract interface for measuring / estimating resource usage for one
    generation call or experiment run.

    Implementors can choose to:
    - Directly measure (via pynvml, psutil, RAPL)
    - Estimate from proxies (token counts, TDP, latency)
    - Combine both approaches

    All three estimate types are returned together so callers can log
    them atomically.
    """

    @abstractmethod
    def measure_energy(
        self,
        latency_ms: float,
        input_tokens: int,
        output_tokens: int,
        model_id: str,
    ) -> EnergyEstimate:
        """
        Estimate or measure the energy consumed for a generation call.

        Parameters
        ----------
        latency_ms : float
            Wall-clock time of the generation call in milliseconds.
        input_tokens : int
        output_tokens : int
        model_id : str

        Returns
        -------
        EnergyEstimate
        """
        ...

    @abstractmethod
    def measure_cost(
        self,
        input_tokens: int,
        output_tokens: int,
        model_id: str,
    ) -> CostEstimate:
        """
        Estimate the monetary cost of a generation call.

        Parameters
        ----------
        input_tokens : int
        output_tokens : int
        model_id : str

        Returns
        -------
        CostEstimate
        """
        ...

    @abstractmethod
    def measure_carbon(
        self,
        energy_estimate: EnergyEstimate,
    ) -> CarbonEstimate:
        """
        Estimate the CO2e emissions for a given energy estimate.

        Parameters
        ----------
        energy_estimate : EnergyEstimate
            Energy result from measure_energy().

        Returns
        -------
        CarbonEstimate
        """
        ...
