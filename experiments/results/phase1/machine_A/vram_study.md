# Phase-1 VRAM study — laptop-a

GPU NVIDIA GeForce RTX 4050 Laptop GPU (6141 MiB), driver 617.14, torch 2.6.0+cu124, Ollama 0.35.1, git `215a48203e` (dirty), recorded 2026-10-04T19:31:49+00:00.

Options: `{"temperature": 0, "seed": 42, "num_predict": 128, "num_ctx": 4096}`. Cold n=3, warm n=5. Energy = NVML energy counter read only at call start and end (MEASURED, GPU board only; power is never polled during a measurement because it perturbs the counter on this driver, see nvml_observer_probe.json). Net = gross − idle power × duration (DERIVED; idle taken at P8 after settling). VRAM = device-wide (WDDM).

| Model | Condition | On GPU | Ollama VRAM MiB | Peak device MiB | Cold s | Warm s | Decode tok/s | Prefill tok/s | Warm J gross | Warm J net | J/out-token | Max °C | Throttle |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| qwen2.5-coder:1.5b | alone | yes (100%) | 1112 | 1429 | 6.60 | 3.45 | 133.9 | 4019 | 102.3 | -0.3 | 0.799 | 80 | none |
| qwen2.5-coder:1.5b | coresident | yes (100%) | 1112 | 1920 | 5.74 | 3.51 | 131.2 | 3260 | 105.7 | 93.4 | 0.826 | 81 | none |
| qwen2.5-coder:3b | alone | yes (100%) | 2059 | 2379 | 8.28 | 4.26 | 78.7 | 2697 | 168.6 | 50.3 | 1.317 | 87 | sw_power_cap, sw_thermal_slowdown |
| qwen2.5-coder:3b | coresident | yes (100%) | 2059 | 2870 | 6.88 | 4.37 | 76.2 | 2422 | 174.2 | 151.6 | 1.361 | 86 | sw_power_cap, sw_thermal_slowdown |
| qwen2.5-coder:7b | alone | NO (82%) | 3992 | 4315 | 15.76 | 9.14 | 21.7 | 1196 | 384.5 | 122.0 | 3.004 | 85 | sw_power_cap, sw_thermal_slowdown |
| qwen2.5-coder:7b | coresident | NO (82%) | 3992 | 4806 | 14.84 | 8.99 | 22.1 | 1230 | 390.1 | 346.5 | 3.048 | 84 | sw_power_cap, sw_thermal_slowdown |

Idle baselines (W, measured after power settled; net energy uses their mean):

- qwen2.5-coder:1.5b / alone: before 30.6 (P0, settled=False), after 28.8 (P0, settled=False)
- qwen2.5-coder:1.5b / coresident: before 2.9 (P8, settled=True), after 4.1 (P8, settled=True)
- qwen2.5-coder:3b / alone: before 29.0 (P8, settled=False), after 26.5 (PNone, settled=False)
- qwen2.5-coder:3b / coresident: before 5.4 (P8, settled=True), after 4.9 (P8, settled=True)
- qwen2.5-coder:7b / alone: before 28.4 (P8, settled=False), after 29.0 (P0, settled=False)
- qwen2.5-coder:7b / coresident: before 5.7 (P8, settled=True), after 4.0 (P8, settled=True)

Encoders (BGE-small + cross-encoder) added 490 MiB device VRAM (torch allocated 222 MiB, reserved 396 MiB).

## Findings and caveats (read before citing any number above)

**Provenance note.** The header says "(dirty)" only because this run's own untracked
result files were counted; the code was exactly commit `215a482` (fixed in `5351267`).
A first run (git `f262ca5`) was discarded: its meter polled GPU power every 50 ms,
which inflates the energy counter on this driver (see `nvml_observer_probe.json`).

1. **7B does not fit fully on the GPU, even alone.** Ollama places 3992 of 4886 MiB
   (81.7%) on the GPU and the rest on the CPU, at num_ctx 4096, with or without the
   encoders loaded. Device peak was 4315 MiB alone and 4806 MiB co-resident (of 6141),
   so the split comes from Ollama's own memory estimate, not from the encoders.
   Unloading the encoders would not change it. Decode rate: 21.7 tok/s alone,
   22.1 tok/s co-resident.
2. **1.5B and 3B fit fully, alone and co-resident.** Co-resident device peaks:
   1920 MiB (1.5B) and 2870 MiB (3B). Encoders add 490 MiB of device VRAM.
3. **Gross energy per warm generation (128 output tokens, ~1,338 prompt tokens),
   co-resident, mean ± sd, n=5:** 1.5B 105.7 ± 10.3 J, 3B 174.2 ± 10.7 J,
   7B 390.1 ± 8.9 J. Alone and co-resident agree within one sd.
4. **"Net of idle" is NOT reliable in the `alone` rows.** Without a CUDA context held
   by the measuring process, this GPU never settled to P8 within 90 s and idled at
   ~27–31 W (P0), so the subtraction removes most of the work energy (1.5B alone: −0.3 J).
   With a context held (`coresident`), it settled to P8 in 2.5 s at 2.9–5.7 W. The
   pipeline always holds a CUDA context (encoders), so the `coresident` net values
   are the relevant ones; use gross for cross-condition comparisons.
5. **Sub-second energy is not measurable with this counter.** One embed + rerank of
   20 chunks (50–180 ms) read 4.8–46.3 J, i.e. physically impossible 30–270 W: the
   counter updates in ~100 ms steps. Treat counter energy as valid only for windows
   of several seconds; short operations must be measured in batches.
6. **The laptop throttles.** 3B and 7B runs reached 84–87 °C with `sw_thermal_slowdown`
   and `sw_power_cap` reported. Throughput stayed stable within runs (7B sd ±0.03–0.14 s),
   but long runs need cooldowns and logged temperatures.
