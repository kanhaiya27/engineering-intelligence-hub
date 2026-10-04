"""
Probe whether NVML queries perturb the GPU energy counter on this machine.

For each query pattern, runs a 3 s idle window, reads the energy counter only at
the start and end, and reports the counter-derived mean power. If the mean power
rises with a query pattern, that query must not run during energy measurements.

Usage: python -m scripts.phase1_nvml_observer_probe [--reps 3] [--out PATH]
"""

from __future__ import annotations

import argparse
import statistics
import time

import pynvml

from core.config import PROJECT_ROOT
from experiments.provenance import collect_provenance, write_json


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--reps", type=int, default=3)
    ap.add_argument("--window", type=float, default=3.0)
    ap.add_argument("--out", default=str(PROJECT_ROOT / "experiments/results/phase1/machine_A/nvml_observer_probe.json"))
    args = ap.parse_args()

    pynvml.nvmlInit()
    h = pynvml.nvmlDeviceGetHandleByIndex(0)

    def safe(f):
        def g():
            try:
                f()
            except pynvml.NVMLError:
                pass
        return g

    patterns = {
        "no_queries": (None, 0.05),
        "power_every_50ms": (lambda: pynvml.nvmlDeviceGetPowerUsage(h), 0.05),
        "power_every_250ms": (lambda: pynvml.nvmlDeviceGetPowerUsage(h), 0.25),
        "mem_temp_clock_every_250ms": (lambda: (pynvml.nvmlDeviceGetMemoryInfo(h),
                                                pynvml.nvmlDeviceGetTemperature(h, pynvml.NVML_TEMPERATURE_GPU),
                                                pynvml.nvmlDeviceGetClockInfo(h, pynvml.NVML_CLOCK_SM)), 0.25),
        "throttle_every_250ms": (safe(lambda: pynvml.nvmlDeviceGetCurrentClocksThrottleReasons(h)), 0.25),
        "counter_every_50ms": (lambda: pynvml.nvmlDeviceGetTotalEnergyConsumption(h), 0.05),
    }
    results = {k: [] for k in patterns}
    for _ in range(args.reps):
        for name, (fn, interval) in patterns.items():
            time.sleep(1.5)
            e0 = pynvml.nvmlDeviceGetTotalEnergyConsumption(h)
            t0 = time.perf_counter()
            while time.perf_counter() - t0 < args.window:
                if fn:
                    fn()
                time.sleep(interval)
            e1 = pynvml.nvmlDeviceGetTotalEnergyConsumption(h)
            results[name].append((e1 - e0) / 1000 / (time.perf_counter() - t0))

    summary = {k: {"mean_w": statistics.fmean(v), "values_w": v} for k, v in results.items()}
    for k, v in summary.items():
        print(f"{k:28} {v['mean_w']:7.1f} W  {[round(x, 1) for x in v['values_w']]}")
    write_json(__import__("pathlib").Path(args.out), {
        "study": "phase1_nvml_observer_probe",
        "provenance": collect_provenance(include_ollama=False),
        "config": {"reps": args.reps, "window_s": args.window, "gpu_state": "idle, no workload"},
        "counter_mean_power_w": summary,
    })
    print("wrote", args.out)


if __name__ == "__main__":
    main()
