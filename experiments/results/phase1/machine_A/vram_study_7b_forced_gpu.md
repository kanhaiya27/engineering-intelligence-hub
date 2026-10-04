# Phase-1 VRAM study — laptop-a

GPU NVIDIA GeForce RTX 4050 Laptop GPU (6141 MiB), driver 617.14, torch 2.6.0+cu124, Ollama 0.35.1, git `653173cd0e`, recorded 2026-10-04T20:46:12+00:00.

Options: `{"temperature": 0, "seed": 42, "num_predict": 128, "num_ctx": 4096, "num_gpu": 999}`. Cold n=3, warm n=5. Energy = NVML energy counter read only at call start and end (MEASURED, GPU board only; power is never polled during a measurement because it perturbs the counter on this driver, see nvml_observer_probe.json). Net = gross − idle power × duration (DERIVED; idle taken at P8 after settling). VRAM = device-wide (WDDM).

| Model | Condition | On GPU | Ollama VRAM MiB | Peak device MiB | Cold s | Warm s | Decode tok/s | Prefill tok/s | Warm J gross | Warm J net | J/out-token | Max °C | Throttle |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| qwen2.5-coder:7b | alone | yes (100%) | 4528 | 4851 | 12.76 | 6.41 | 38.3 | 1489 | 318.6 | 140.0 | 2.489 | 89 | hw_slowdown, hw_thermal_slowdown, sw_power_cap, sw_thermal_slowdown |
| qwen2.5-coder:7b | coresident | yes (100%) | 4528 | 5342 | 11.00 | 6.44 | 38.1 | 1444 | 306.8 | 262.1 | 2.397 | 88 | sw_power_cap, sw_thermal_slowdown |

Idle baselines (W, measured after power settled; net energy uses their mean):

- qwen2.5-coder:7b / alone: before 28.9 (P0, settled=False), after 26.8 (PNone, settled=False)
- qwen2.5-coder:7b / coresident: before 5.2 (P8, settled=True), after 8.7 (P8, settled=True)

Encoders (BGE-small + cross-encoder) added 490 MiB device VRAM (torch allocated 222 MiB, reserved 396 MiB).

## Findings (compare with `vram_study.json`, same protocol, Ollama's default placement)

| 7B Q4_K_M, warm n=5 | Default placement | `num_gpu=999` (all layers on GPU) |
|---|---|---|
| Resident on GPU | 3,992 of 4,886 MiB (82%) | 4,528 of 4,528 MiB (100%) |
| Device peak, co-resident with encoders | 4,806 MiB | 5,342 MiB of 6,141 |
| Decode | 22.1 ± 0.1 tok/s | 38.1 ± 0.4 tok/s (+72%) |
| Warm call | 8.99 s | 6.44 s |
| Gross GPU energy per call | 390.1 ± 8.9 J | 306.8 ± 11.8 J (−21%) |
| Energy per output token | 3.05 J | 2.40 J |

1. Forcing all layers onto the GPU fits on this 6 GB card at num_ctx 4096 even with the
   encoders resident (≈800 MiB headroom), and is faster and cheaper per call. No sign of
   WDDM system-memory fallback: residency is 100%, device memory stays below the total,
   and throughput rose with very low variance.
2. The total model footprint is smaller when fully on the GPU (4,528 vs 4,886 MiB): the
   split placement carries extra CPU-side buffers.
3. Headroom is specific to num_ctx 4096; a larger context grows the KV cache (measured in
   the long-context probe).
4. The alone run reached 89 °C with `hw_thermal_slowdown`; throughput stayed stable
   within the run (sd 0.1 tok/s), but long runs need cooldowns and logged temperature.
5. "Net of idle" is not valid for the `alone` row (no settled P8 baseline), as in the
   main study; use gross energy.
