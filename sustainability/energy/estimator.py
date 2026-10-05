"""
Engineering Intelligence Hub — Energy Estimator
================================================
Provides energy consumption estimates for LLM generation calls.

Estimation approach (Phase-0):
  - For API-based models: latency × CPU/GPU TDP proxy (no direct measurement)
  - For local models: attempt GPU utilisation via pynvml if available,
    fall back to TDP proxy otherwise

This is an ESTIMATE. Actual energy requires hardware power measurement
(RAPL, NVML power readings, smart-metered PDUs). The estimate is
reported with its method clearly flagged.

See sustainability/base.py for full system boundary declaration.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional

import psutil


class EnergyEstimationMethod(str, Enum):
    """How the energy was estimated/measured."""
    TDP_PROXY = "tdp_proxy"             # latency × TDP fraction
    NVML_MEASUREMENT = "nvml_measurement"  # Direct GPU power via pynvml
    # One instantaneous NVML power reading x duration. It is NOT integrated over
    # the call (F3), so it is an estimate, not a measurement. Integrated GPU energy
    # comes from sustainability/energy/nvml_meter.py (energy counter).
    NVML_POWER_SAMPLE = "nvml_power_sample"
    RAPL_MEASUREMENT = "rapl_measurement"  # Intel RAPL (Linux only)
    NOT_AVAILABLE = "not_available"      # Could not estimate


@dataclass
class EnergyEstimate:
    """Result of one energy estimation."""

    energy_joules: float
    method: EnergyEstimationMethod
    # Component breakdown (may be zero if not measured)
    cpu_energy_joules: float = 0.0
    gpu_energy_joules: float = 0.0
    # Uncertainty flag
    is_estimate: bool = True
    notes: str = ""
    # Raw inputs used
    latency_ms: float = 0.0
    input_tokens: int = 0
    output_tokens: int = 0
    cpu_utilisation_pct: Optional[float] = None
    gpu_utilisation_pct: Optional[float] = None


class EnergyEstimator:
    """
    Estimates energy consumption for generation calls.

    Parameters
    ----------
    cpu_tdp_watts : float
        CPU TDP in watts (used as proxy when direct measurement unavailable).
        Default: 45W (i7-12650H TDP).
    gpu_tdp_watts : float
        GPU TGP/TDP in watts.
        Default: 60W (RTX 4050 Laptop GPU TGP).
    pue_factor : float
        Power Usage Effectiveness — data centre overhead multiplier.
        Set to 1.0 for local inference (no data centre overhead).
        Set to 1.1–1.5 for cloud inference.
    """

    def __init__(
        self,
        cpu_tdp_watts: float = 45.0,
        gpu_tdp_watts: float = 60.0,
        pue_factor: float = 1.0,
    ) -> None:
        self.cpu_tdp_watts = cpu_tdp_watts
        self.gpu_tdp_watts = gpu_tdp_watts
        self.pue_factor = pue_factor
        self._nvml_available = self._check_nvml()
        # F5: psutil.cpu_percent(interval=None) returns a meaningless 0.0 on its
        # first call in a process; later calls cover the time since the previous
        # call. Priming it here avoids the 0.0; the value is still not tied to one
        # call, which is why CPU energy is always labelled an estimate.
        try:
            psutil.cpu_percent(interval=None)
        except Exception:  # noqa: BLE001
            pass

    @classmethod
    def from_settings(cls, sustainability_settings: Optional[object] = None) -> "EnergyEstimator":
        """
        Build an estimator from `settings.sustainability`.

        Use this at every production call site so the configured CPU/GPU TDP
        values actually reach the estimator. The bare constructor hardcodes the
        development laptop's figures (45 W / 60 W), which silently misreports
        energy on any other machine.
        """
        if sustainability_settings is None:
            from core.config import settings

            sustainability_settings = settings.sustainability

        return cls(
            cpu_tdp_watts=getattr(sustainability_settings, "cpu_tdp_watts", 45.0),
            gpu_tdp_watts=getattr(sustainability_settings, "gpu_tdp_watts", 60.0),
        )

    @staticmethod
    def _check_nvml() -> bool:
        """Return True if pynvml is installed and a GPU is accessible."""
        try:
            import pynvml  # type: ignore[import]
            pynvml.nvmlInit()
            return True
        except Exception:
            return False

    def estimate(
        self,
        latency_ms: float,
        input_tokens: int,
        output_tokens: int,
        model_id: str,
        is_local_model: bool = False,
    ) -> EnergyEstimate:
        """
        Estimate energy for a single generation call.

        For API models (is_local_model=False):
          - We measure CPU utilisation via psutil during the call.
          - GPU energy is NOT measured (inference runs on provider hardware).
          - Total = CPU energy (local) only.

        For local models (is_local_model=True):
          - Attempt GPU measurement via NVML.
          - Fall back to GPU TDP proxy.

        Parameters
        ----------
        latency_ms : float
        input_tokens : int
        output_tokens : int
        model_id : str
        is_local_model : bool
        """
        latency_seconds = latency_ms / 1000.0

        # --- CPU energy estimation ---
        try:
            cpu_util = psutil.cpu_percent(interval=None) / 100.0
        except Exception:
            cpu_util = 0.5  # assume 50% if measurement fails

        cpu_energy_j = self.cpu_tdp_watts * cpu_util * latency_seconds

        # --- GPU energy estimation ---
        gpu_energy_j = 0.0
        gpu_util = None
        method = EnergyEstimationMethod.TDP_PROXY

        if is_local_model:
            sample = self._measure_gpu_energy_nvml(latency_seconds) if self._nvml_available else None
            if sample is not None:
                gpu_energy_j, gpu_util = sample
                method = EnergyEstimationMethod.NVML_POWER_SAMPLE
            else:
                # TDP proxy: assume 70% GPU utilisation for active inference
                gpu_util_fraction = 0.70
                gpu_energy_j = self.gpu_tdp_watts * gpu_util_fraction * latency_seconds
                gpu_util = gpu_util_fraction * 100

        total_energy_j = (cpu_energy_j + gpu_energy_j) * self.pue_factor

        return EnergyEstimate(
            energy_joules=round(total_energy_j, 6),
            method=method,
            cpu_energy_joules=round(cpu_energy_j, 6),
            gpu_energy_joules=round(gpu_energy_j, 6),
            is_estimate=True,
            notes=(
                f"{'Local' if is_local_model else 'API'} model. "
                f"PUE={self.pue_factor}. "
                f"CPU TDP proxy={self.cpu_tdp_watts}W. "
                f"{'NVML single power sample x duration' if method == EnergyEstimationMethod.NVML_POWER_SAMPLE else 'GPU TDP proxy'}."
            ),
            latency_ms=latency_ms,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cpu_utilisation_pct=round(cpu_util * 100, 2),
            gpu_utilisation_pct=round(gpu_util, 2) if gpu_util is not None else None,
        )

    def _measure_gpu_energy_nvml(self, duration_seconds: float):
        """One NVML power reading x duration, or None if the read fails.

        Returning None (instead of TDP-proxy numbers) lets the caller label the
        result as the TDP proxy it then is (F2: a failed read used to be
        reported as an NVML measurement).
        """
        try:
            import pynvml  # type: ignore[import]
            handle = pynvml.nvmlDeviceGetHandleByIndex(0)
            power_mw = pynvml.nvmlDeviceGetPowerUsage(handle)  # milliwatts
            util_info = pynvml.nvmlDeviceGetUtilizationRates(handle)
            power_w = power_mw / 1000.0
            energy_j = power_w * duration_seconds
            return energy_j, float(util_info.gpu)
        except Exception:
            return None
