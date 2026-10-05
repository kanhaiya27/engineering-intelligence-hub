# Long-context probe, part 2 — laptop-a

GPU NVIDIA GeForce RTX 4050 Laptop GPU (6141 MiB), driver 617.14, Ollama 0.35.1, git `a02e71bf28` (dirty), recorded 2026-10-05T09:02:53+00:00. Encoders resident: True. Prompt = real corpus evidence filled to num_ctx - 256 - 32 tokens; temperature 0, seed 42, num_predict 256. Each condition starts unloaded; a condition with any call above 90 °C is discarded and repeated after cooling to 65 °C (start temperature in the JSON); 1 cold + 2 warm calls. Energy = NVML counter at start/end (MEASURED, GPU board, gross).

| Model | Layers | num_ctx | Start °C | Prompt tok | On GPU | Peak device MiB | Saturated | Cold s | Warm s | Prefill tok/s | Decode tok/s | Warm J | Max °C | Throttle | Errors |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| qwen2.5-coder:1.5b | forced | 12288 | 47 | 11716 | 100% | 2338 | no | 8.5 | 6.8 | 5270 | 111.4 | 348.6 | 82 | hw_slowdown, hw_thermal_slowdown, sw_thermal_slowdown | none |
| qwen2.5-coder:3b | forced | 12288 | 50 | 11716 | 100% | 3368 | no | 11.3 | 8.5 | 2981 | 68.6 | 478.4 | 84 | sw_power_cap, sw_thermal_slowdown | none |
