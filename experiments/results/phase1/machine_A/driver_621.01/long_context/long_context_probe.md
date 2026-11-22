# Long-context probe, part 2 — laptop-a

GPU NVIDIA GeForce RTX 4050 Laptop GPU (6141 MiB), driver 621.01, Ollama 0.35.1, git `c6043927cf` (dirty), recorded 2026-11-22T20:42:39+00:00. Encoders resident: True. Prompt = real corpus evidence filled to num_ctx - 256 - 32 tokens; temperature 0, seed 42, num_predict 256. Each condition starts unloaded; a condition with any call above 90 °C is discarded and repeated after cooling to 65 °C (start temperature in the JSON); 1 cold + 2 warm calls. Energy = NVML counter at start/end (MEASURED, GPU board, gross).

| Model | Layers | num_ctx | Start °C | Prompt tok | On GPU | Peak device MiB | Saturated | Cold s | Warm s | Prefill tok/s | Decode tok/s | Warm J | Max °C | Throttle | Errors |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| qwen2.5-coder:7b | forced | 12288 | 51 | 11990 | 100% | 5908 | no | 24.8 | 13.5 | 1387 | 34.2 | 756.4 | 86 | hw_slowdown, hw_thermal_slowdown, sw_power_cap, sw_thermal_slowdown | none |
| qwen2.5-coder:7b | forced | 16384 | 57 | 16010 | 100% | 6088 | YES | 21.7 | 17.3 | 1249 | 32.7 | 929.5 | 88 | hw_slowdown, hw_thermal_slowdown, sw_power_cap, sw_thermal_slowdown | none |
| qwen2.5-coder:7b | forced | 20480 | 59 | 19978 | 100% | 6112 | YES | 92.9 | 87.3 | 242 | 30.8 | 3361.2 | 87 | sw_thermal_slowdown | none |
