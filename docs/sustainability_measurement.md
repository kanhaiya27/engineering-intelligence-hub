# Sustainability & Energy Measurement Methodology

## Overview

The Engineering Intelligence Hub measures and models computational energy, monetary cost, and greenhouse gas emissions across all AI operations.

---

## 1. System Boundaries & Distinction

| Inference Type | Measurement Method | Accuracy / Tier | Hardware Monitored |
|---|---|---|---|
| **Local Model Inference** (e.g. BGE Small Embeddings) | **Direct Hardware Measurement** via NVIDIA NVML (`pynvml.nvmlDeviceGetPowerUsage`) | Tier 1 (Direct Measurement) | NVIDIA GeForce RTX 4050 Laptop GPU |
| **API / Cloud LLM Calls** (e.g. GPT-4o-mini, Claude) | **Model Proxy Estimation** via thermal design power (TDP) proxy equation | Tier 2 (Modelled Estimate) | Host CPU execution + cloud cluster proxy |

> [!IMPORTANT]
> To preserve research integrity, measured GPU energy and estimated API energy are never conflated without explicit labelling. All outputs in logs and databases declare `is_estimate: bool` and `energy_estimation_method: str`.

---

## 2. Energy Formulation

### Local GPU Inference
$$E_{\text{local}} = \int_{0}^{T} P(t) \, dt \approx \sum_{i} P_i \cdot \Delta t$$
Sampled via NVML device power readings in milliwatts, converted to Joules ($1 \text{ W} = 1 \text{ J/s}$).

### Cloud API Inference (TDP Proxy)
$$E_{\text{est}} = \left( P_{\text{server\_idle}} + \frac{P_{\text{server\_active}} \times \text{tokens}}{C_{\text{throughput}}} \right) \times T_{\text{latency}}$$

---

## 3. Carbon Footprint (CO2e)

Emissions are estimated using regional carbon intensity factors:

$$\text{CO}_2\text{e (grams)} = E_{\text{total}} (\text{kWh}) \times I_{\text{grid}} \left( \frac{\text{gCO}_2\text{e}}{\text{kWh}} \right)$$

Default reference intensities ($I_{\text{grid}}$):
- UK National Grid (2024): $233.0 \text{ gCO}_2\text{e/kWh}$
- EU Average (2023): $251.0 \text{ gCO}_2\text{e/kWh}$
- US Average (2023): $386.0 \text{ gCO}_2\text{e/kWh}$
- India Average (2023): $713.0 \text{ gCO}_2\text{e/kWh}$
- 100% Renewable: $0.0 \text{ gCO}_2\text{e/kWh}$

---

## 4. Monetary Cost

Calculated per million tokens from public provider pricing tables:
$$\text{Cost} = \frac{N_{\text{input}}}{10^6} \times \text{Price}_{\text{input}} + \frac{N_{\text{output}}}{10^6} \times \text{Price}_{\text{output}}$$
