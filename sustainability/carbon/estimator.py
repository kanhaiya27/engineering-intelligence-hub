"""
Engineering Intelligence Hub — Carbon Footprint Estimator
=========================================================
Estimates CO2-equivalent (CO2e) emissions for LLM generation calls.

METHODOLOGY
-----------
CO2e = Energy (kWh) × Carbon Intensity (gCO2e/kWh)

Carbon intensity varies by:
- Geographic region of inference (cloud region or local grid)
- Time of day (for renewable-energy-heavy grids)

Default: UK national grid average for 2024 (~233 gCO2e/kWh)
Source:  National Grid ESO, Carbon Intensity API (carbonintensity.org.uk)

IMPORTANT LIMITATIONS
---------------------
1. This estimate covers only the inference energy within our system boundary
   (see sustainability/base.py for the full boundary declaration).
2. It does NOT include:
   - Embodied carbon of hardware
   - Training energy of LLMs
   - Network transmission energy
3. Carbon intensity values must be updated per experiment region.
4. Always disclose the carbon intensity value used when reporting results.
5. These estimates are for comparative research purposes — not for
   formal environmental impact assessments or carbon accounting.

References
----------
- Patterson et al. (2021). "Carbon and the Carbon Footprint of ML."
  arXiv:2104.10350
- Lannelongue et al. (2021). "Green Algorithms: Quantifying the Carbon
  Footprint of Computation." Adv Sci. DOI: 10.1002/advs.202100707
- National Grid ESO Carbon Intensity: https://carbonintensity.org.uk
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from sustainability.energy.estimator import EnergyEstimate


# ---------------------------------------------------------------------------
# Reference carbon intensities (gCO2e/kWh)
# Update these per experiment region.
# ---------------------------------------------------------------------------

CARBON_INTENSITIES_GCO2_PER_KWH = {
    "uk_national_grid_2024": 233.0,
    "eu_average_2023": 251.0,
    "us_average_2023": 386.0,
    "india_average_2023": 713.0,
    "france_2023": 56.0,     # High nuclear fraction
    "germany_2023": 385.0,
    "renewable_100pct": 0.0,  # Theoretical maximum for RE-powered inference
}

DEFAULT_REGION = "uk_national_grid_2024"


@dataclass
class CarbonEstimate:
    """CO2e estimate for a single generation call."""

    co2e_grams: float
    energy_joules: float
    carbon_intensity_gco2_per_kwh: float
    region: str
    is_estimate: bool = True
    methodology: str = ""
    notes: str = ""


class CarbonEstimator:
    """
    Estimates CO2e emissions from energy estimates.

    Parameters
    ----------
    region : str
        Region key from CARBON_INTENSITIES_GCO2_PER_KWH, or
        'custom' (in which case custom_intensity_gco2_kwh must be set).
    custom_intensity_gco2_kwh : float, optional
        Custom carbon intensity if region='custom'.
    """

    def __init__(
        self,
        region: str = DEFAULT_REGION,
        custom_intensity_gco2_kwh: Optional[float] = None,
    ) -> None:
        if region == "custom":
            if custom_intensity_gco2_kwh is None:
                raise ValueError(
                    "custom_intensity_gco2_kwh must be set when region='custom'."
                )
            self._intensity = custom_intensity_gco2_kwh
        else:
            if region not in CARBON_INTENSITIES_GCO2_PER_KWH:
                raise ValueError(
                    f"Unknown region '{region}'. "
                    f"Choose from: {list(CARBON_INTENSITIES_GCO2_PER_KWH.keys())} "
                    "or use region='custom' with custom_intensity_gco2_kwh."
                )
            self._intensity = CARBON_INTENSITIES_GCO2_PER_KWH[region]

        self.region = region

    @property
    def carbon_intensity(self) -> float:
        """Current carbon intensity in gCO2e/kWh."""
        return self._intensity

    def estimate(self, energy_estimate: EnergyEstimate) -> CarbonEstimate:
        """
        Compute CO2e from an energy estimate.

        Parameters
        ----------
        energy_estimate : EnergyEstimate

        Returns
        -------
        CarbonEstimate
        """
        # Convert joules to kWh: 1 kWh = 3,600,000 J
        energy_kwh = energy_estimate.energy_joules / 3_600_000.0
        co2e_grams = energy_kwh * self._intensity

        return CarbonEstimate(
            co2e_grams=round(co2e_grams, 8),
            energy_joules=energy_estimate.energy_joules,
            carbon_intensity_gco2_per_kwh=self._intensity,
            region=self.region,
            is_estimate=True,
            methodology=(
                "CO2e = (energy_joules / 3,600,000) × carbon_intensity_gCO2e_per_kWh. "
                "Inference-stage only. See sustainability/base.py for boundary declaration."
            ),
            notes=(
                f"Region: {self.region}. "
                f"Energy method: {energy_estimate.method}. "
                "Always disclose carbon intensity and region when reporting results."
            ),
        )

    @classmethod
    def list_regions(cls) -> dict:
        """Return all available region intensities."""
        return dict(CARBON_INTENSITIES_GCO2_PER_KWH)
