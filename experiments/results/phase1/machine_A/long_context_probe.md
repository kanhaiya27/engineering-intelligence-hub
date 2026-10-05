# Long-context probe, part 2 — laptop-a

GPU NVIDIA GeForce RTX 4050 Laptop GPU (6141 MiB), driver 617.14, Ollama 0.35.1, git `a02e71bf28`, recorded 2026-10-05T08:49:24+00:00. Encoders resident: True. Prompt = real corpus evidence filled to num_ctx - 256 - 32 tokens; temperature 0, seed 42, num_predict 256. Each condition starts unloaded; a condition with any call above 90 °C is discarded and repeated after cooling to 65 °C (start temperature in the JSON); 1 cold + 2 warm calls. Energy = NVML counter at start/end (MEASURED, GPU board, gross).

| Model | Layers | num_ctx | Start °C | Prompt tok | On GPU | Peak device MiB | Saturated | Cold s | Warm s | Prefill tok/s | Decode tok/s | Warm J | Max °C | Throttle | Errors |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| qwen2.5-coder:7b | forced | 4096 | 46 | 3668 | 100% | 5450 | no | 18.2 | 10.3 | 1815 | 37.0 | 691.4 | 85 | hw_slowdown, hw_thermal_slowdown, sw_thermal_slowdown | none |
| qwen2.5-coder:7b | forced | 8192 | 50 | 7608 | 100% | 5678 | no | 12.7 | 9.1 | 1639 | 35.4 | 522.1 | 85 | hw_slowdown, hw_thermal_slowdown, sw_thermal_slowdown | none |
| qwen2.5-coder:7b | forced | 12288 | 51 | 11716 | 100% | 5906 | no | 16.6 | 12.7 | 1491 | 34.6 | 762.8 | 85 | hw_slowdown, hw_thermal_slowdown, sw_power_cap, sw_thermal_slowdown | none |
| qwen2.5-coder:7b | forced | 16384 | 52 | 16056 | 100% | 6088 | YES | 19.6 | 19.4 | 1159 | 33.1 | 1022.4 | 86 | hw_slowdown, hw_thermal_slowdown, sw_power_cap, sw_thermal_slowdown | none |
| qwen2.5-coder:7b | forced | 20480 | 53 | 20180 | 100% | 6112 | YES | 94.5 | 90.4 | 237 | 30.9 | 3214.6 | 82 | none | none |
| qwen2.5-coder:7b | forced | 24576 | 53 | 23986 | 100% | 6078 | YES | 152.9 | 169.9 | 149 | 14.2 | 5442.8 | 72 | none | none |
| qwen2.5-coder:7b | default | 4096 | 52 | 3672 | 82% | 4914 | no | 22.7 | 10.7 | 1463 | 20.1 | 489.4 | 82 | sw_thermal_slowdown | none |
| qwen2.5-coder:7b | default | 8192 | 52 | 7606 | 76% | 4826 | no | 18.9 | 14.1 | 1289 | 13.6 | 602.8 | 85 | sw_power_cap, sw_thermal_slowdown | none |
| qwen2.5-coder:7b | default | 12288 | 52 | 11714 | 73% | 4860 | no | 27.0 | 22.0 | 1217 | 9.3 | 841.8 | 85 | hw_slowdown, hw_thermal_slowdown, sw_power_cap, sw_thermal_slowdown | none |
| qwen2.5-coder:7b | default | 16384 | 52 | 16056 | 73% | 5046 | no | 32.4 | 26.9 | 1112 | 6.6 | 1094.6 | 86 | hw_slowdown, hw_thermal_slowdown, sw_power_cap, sw_thermal_slowdown | none |
| qwen2.5-coder:7b | default | 20480 | 53 | 20179 | 67% | 4886 | no | 42.2 | 43.9 | 845 | 4.0 | 1560.2 | 86 | hw_slowdown, hw_thermal_slowdown, sw_power_cap, sw_thermal_slowdown | none |
| qwen2.5-coder:7b | default | 24576 | 53 | 23986 | 64% | 4850 | no | 65.5 | 53.1 | 913 | 3.3 | 1959.4 | 86 | hw_slowdown, hw_thermal_slowdown, sw_power_cap, sw_thermal_slowdown | none |
