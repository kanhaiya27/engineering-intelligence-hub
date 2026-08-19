"""Tests for sustainability estimators."""

from __future__ import annotations

import pytest

from sustainability.cost.estimator import CostEstimator
from sustainability.carbon.estimator import CarbonEstimator, CARBON_INTENSITIES_GCO2_PER_KWH
from sustainability.energy.estimator import EnergyEstimator, EnergyEstimationMethod


class TestCostEstimator:
    def test_known_model_cost(self):
        est = CostEstimator()
        result = est.estimate(
            input_tokens=1000,
            output_tokens=500,
            model_id="gpt-4o-mini",
        )
        # gpt-4o-mini: $0.15/1M in, $0.60/1M out
        expected_input = (1000 / 1_000_000) * 0.15
        expected_output = (500 / 1_000_000) * 0.60
        expected_total = expected_input + expected_output
        assert result.total_cost_usd == pytest.approx(expected_total, rel=1e-6)
        assert result.is_estimate is True

    def test_unknown_model_uses_fallback(self):
        est = CostEstimator()
        result = est.estimate(
            input_tokens=1000,
            output_tokens=1000,
            model_id="unknown-model-xyz",
        )
        assert result.total_cost_usd > 0
        assert "FALLBACK" in result.notes

    def test_local_model_zero_cost(self):
        est = CostEstimator()
        result = est.estimate(
            input_tokens=5000,
            output_tokens=2000,
            model_id="local",
        )
        assert result.total_cost_usd == 0.0

    def test_register_custom_model(self):
        est = CostEstimator()
        est.register_model_pricing("my-custom-model", 1.00, 3.00)
        result = est.estimate(1_000_000, 1_000_000, "my-custom-model")
        assert result.total_cost_usd == pytest.approx(4.00, rel=1e-6)

    def test_prefix_matching(self):
        est = CostEstimator()
        # "gpt-4o-mini-2024-07-18" should match "gpt-4o-mini" pricing
        result = est.estimate(1000, 500, "gpt-4o-mini-2024-07-18")
        # Should NOT use fallback pricing
        assert "FALLBACK" not in result.notes


class TestCarbonEstimator:
    def test_uk_grid_intensity(self):
        est = CarbonEstimator(region="uk_national_grid_2024")
        assert est.carbon_intensity == pytest.approx(233.0)

    def test_co2_calculation(self):
        from sustainability.energy.estimator import EnergyEstimate, EnergyEstimationMethod
        energy = EnergyEstimate(
            energy_joules=3600.0,  # 1 Wh = 3600 J → 1 Wh / 1000 = 0.001 kWh
            method=EnergyEstimationMethod.TDP_PROXY,
        )
        # 0.001 kWh × 233 gCO2/kWh = 0.233 grams CO2e
        est = CarbonEstimator(region="uk_national_grid_2024")
        result = est.estimate(energy)
        assert result.co2e_grams == pytest.approx(0.233, rel=1e-4)

    def test_renewable_zero_carbon(self):
        from sustainability.energy.estimator import EnergyEstimate, EnergyEstimationMethod
        energy = EnergyEstimate(
            energy_joules=36000.0,  # 10 Wh
            method=EnergyEstimationMethod.TDP_PROXY,
        )
        est = CarbonEstimator(region="renewable_100pct")
        result = est.estimate(energy)
        assert result.co2e_grams == 0.0

    def test_custom_region(self):
        est = CarbonEstimator(region="custom", custom_intensity_gco2_kwh=500.0)
        assert est.carbon_intensity == 500.0

    def test_invalid_region_raises(self):
        with pytest.raises(ValueError, match="Unknown region"):
            CarbonEstimator(region="mars_grid_2030")

    def test_custom_without_intensity_raises(self):
        with pytest.raises(ValueError):
            CarbonEstimator(region="custom")

    def test_list_regions(self):
        regions = CarbonEstimator.list_regions()
        assert "uk_national_grid_2024" in regions
        assert "renewable_100pct" in regions


class TestEnergyEstimator:
    def test_basic_estimate(self):
        est = EnergyEstimator(cpu_tdp_watts=45.0, gpu_tdp_watts=60.0)
        result = est.estimate(
            latency_ms=1000.0,
            input_tokens=500,
            output_tokens=300,
            model_id="gpt-4o-mini",
            is_local_model=False,
        )
        assert result.energy_joules >= 0.0
        assert result.is_estimate is True
        assert result.method == EnergyEstimationMethod.TDP_PROXY
        # GPU should be 0 for API models
        assert result.gpu_energy_joules == 0.0

    def test_local_model_has_gpu_energy(self):
        est = EnergyEstimator(cpu_tdp_watts=45.0, gpu_tdp_watts=60.0)
        result = est.estimate(
            latency_ms=2000.0,
            input_tokens=1000,
            output_tokens=500,
            model_id="local/llama-3-8b",
            is_local_model=True,
        )
        # GPU energy should be > 0 for local models
        assert result.gpu_energy_joules > 0.0

    def test_zero_latency_returns_zero(self):
        est = EnergyEstimator()
        result = est.estimate(0.0, 0, 0, "gpt-4o-mini", is_local_model=False)
        assert result.energy_joules == pytest.approx(0.0, abs=1e-9)
